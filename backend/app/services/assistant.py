"""The offline assistant: routes text to intents and carries them out.

``AssistantService`` is UI-independent. The Windows app calls it in-process and
the FastAPI layer wraps it for Android. Online AI arrives in a later stage; any
request it can't handle offline gets an honest "can't do that offline" reply
instead of being silently dropped.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Callable

from app.automation.actions import (
    ActionError,
    ActionProposal,
    AutomationPolicy,
    Executor,
    SystemExecutor,
)
from app.core import calc, i18n, router, timeparse
from app.core.config import Settings
from app.core.language import REPLY_LANGUAGE, detect_language
from app.database.store import Store, parse_iso
from app.services.ai_provider import AIProvider, ProviderError, configured_provider

log = logging.getLogger("aven.assistant")

MAX_MESSAGE_LENGTH = 2000
PENDING_TTL = timedelta(minutes=5)


@dataclass
class Reply:
    text: str
    intent: str
    conversation_id: str
    language: str
    needs_input: str | None = None  # "confirmation" | "clarification" | None
    stop_speaking: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "conversation_id": self.conversation_id,
            "language": self.language,
            "needs_input": self.needs_input,
            "stop_speaking": self.stop_speaking,
            "data": self.data,
        }


@dataclass
class _Pending:
    kind: str  # "confirm_action" | "reminder_when" | "reminder_meridiem"
    expires_at: datetime
    payload: dict[str, Any]


def _default_clock() -> datetime:
    return datetime.now().astimezone()


class AssistantService:
    def __init__(
        self,
        store: Store,
        settings: Settings | None = None,
        executor: Executor | None = None,
        policy: AutomationPolicy | None = None,
        clock: Callable[[], datetime] = _default_clock,
        allow_actions: bool = True,
        ai_provider: AIProvider | None = None,
    ) -> None:
        # The HTTP API passes allow_actions=False: a remote request must not be
        # able to launch programs on this computer until device pairing exists.
        self._allow_actions = allow_actions
        self._store = store
        self._settings = settings or Settings()
        self._policy = policy or AutomationPolicy(
            approved_dirs=self._settings.approved_dirs,
            extra_apps=self._settings.extra_apps,
            confirm_actions=self._settings.confirm_actions,
        )
        self._executor: Executor = executor or SystemExecutor()
        self._ai_provider = ai_provider if ai_provider is not None else configured_provider(self._settings)
        self._clock = clock
        self._pending: dict[str, _Pending] = {}
        self._last_language: dict[str, str] = {}
        self._greetings: dict[str, int] = {}
        self._lock = threading.RLock()

    # -- public API -------------------------------------------------------------

    def handle_text(
        self, text: str, conversation_id: str | None = None, private: bool = False
    ) -> Reply:
        with self._lock:
            return self._handle(text, conversation_id, private)

    # -- core -------------------------------------------------------------------

    def _handle(self, text: str, conversation_id: str | None, private: bool) -> Reply:
        if conversation_id is not None and not self._store.valid_conversation_id(conversation_id):
            conversation_id = None
        conv = conversation_id or self._store.new_conversation_id()
        persist = self._settings.store_history and not private

        if len(text) > MAX_MESSAGE_LENGTH:
            return Reply(
                f"That message is too long. Please keep it under {MAX_MESSAGE_LENGTH} characters.",
                "error", conv, "en",
            )

        command = router.strip_wake(text) or text
        language = detect_language(command, default=self._last_language.get(conv, "en"))
        self._last_language[conv] = language
        lang = REPLY_LANGUAGE[language]

        if persist:
            self._safe_store(lambda: self._store.add_message(conv, "user", text, language))

        reply = self._dispatch(text, command, conv, language, lang)

        if persist:
            self._safe_store(
                lambda: self._store.add_message(conv, "assistant", reply.text, reply.language)
            )
        return reply

    def _safe_store(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception:  # noqa: BLE001 - history must never break a command
            log.exception("Could not save conversation history")

    def _dispatch(self, raw: str, command: str, conv: str, language: str, lang: str) -> Reply:
        now = self._clock()

        pending = self._pending.pop(conv, None)
        if pending is not None and pending.expires_at < now:
            pending = None
        if pending is not None:
            handled = self._resolve_pending(pending, raw, command, conv, language, now)
            if handled is not None:
                return handled
            # The reply wasn't an answer; treat it as a fresh command.

        intent = router.route(raw)
        make = lambda txt, **kw: Reply(txt, intent.name, conv, language, **kw)  # noqa: E731

        match intent.name:
            case "empty":
                return make("I didn't catch anything. What would you like to do?")
            case "stop":
                return make(i18n.text("stop", lang), stop_speaking=True)
            case "greeting":
                count = self._greetings.get(conv, 0)
                self._greetings[conv] = count + 1
                return make(i18n.text("greeting", lang, count))
            case "how_are_you":
                return make(i18n.text("how_are_you", lang))
            case "help":
                return make(i18n.text("help", lang))
            case "time":
                return make(f"It's {self._clock_time(now)}.")
            case "date":
                return make(f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}.")
            case "calc":
                return self._calc(intent, make)
            case "note_add":
                note = self._store.add_note(intent.args["text"])
                return make(f"Saved note #{note.id}: {note.text}", data={"note_id": note.id})
            case "note_list":
                return self._notes(self._store.list_notes(10), "You don't have any notes yet.", make)
            case "note_search":
                found = self._store.search_notes(intent.args["query"], 10)
                return self._notes(found, "I couldn't find any notes matching that.", make)
            case "task_add":
                task = self._store.add_task(intent.args["title"])
                return make(f"Added task #{task.id}: {task.title}", data={"task_id": task.id})
            case "task_list":
                return self._tasks(make)
            case "task_done":
                return self._task_done(intent.args["id"], make)
            case "reminder_list":
                return self._reminders(make)
            case "reminder_add":
                return self._reminder_add(intent.args["text"], conv, language, now)
            case "open":
                if not self._allow_actions:
                    return make(
                        "Opening apps and folders isn't available over this connection. "
                        "Use Aven on the computer itself."
                    )
                return self._open(intent.args["target"], conv, language)
            case _:
                if self._ai_provider is not None:
                    try:
                        return make(self._ai_provider.generate(raw, language))
                    except ProviderError as exc:
                        log.warning("Online AI failed; using offline fallback: %s", exc)
                return make(i18n.text("fallback", lang))

    # -- pending follow-ups -----------------------------------------------------

    def _resolve_pending(
        self, pending: _Pending, raw: str, command: str, conv: str, language: str, now: datetime
    ) -> Reply | None:
        cancelled = router.is_no(command) or router.route(raw).name == "stop"

        if pending.kind == "confirm_action":
            if router.is_yes(command):
                return self._run_action(pending.payload["target"], conv, language, confirmed=True)
            if cancelled:
                return Reply("Okay, I won't do that.", "action_cancelled", conv, language)
            return None

        if cancelled:
            return Reply("Okay, I've dropped that reminder.", "reminder_cancelled", conv, language)

        title = pending.payload["title"]
        if pending.kind == "reminder_meridiem":
            meridiem = timeparse.parse_meridiem(command)
            if meridiem is None:
                if router.route(raw).name != "unknown":
                    return None  # a real command: drop the question and handle it
                pending.expires_at = now + PENDING_TTL
                self._pending[conv] = pending  # unintelligible: ask again
                return Reply(
                    "Please answer AM or PM.", "reminder_add", conv, language,
                    needs_input="clarification",
                )
            return self._finish_absolute(
                pending.payload["parse"], title, meridiem, conv, language, now
            )

        if pending.kind == "reminder_when":
            parsed = timeparse.parse_when(command, now)
            if parsed.kind == "none" and command[:1].isdigit():
                parsed = timeparse.parse_when("at " + command, now)  # bare "7 pm"
            if parsed.kind in ("none", "invalid"):
                return None
            parsed = _with_title(parsed, title)
            return self._schedule(parsed, conv, language, now)
        return None

    # -- intent handlers --------------------------------------------------------

    @staticmethod
    def _clock_time(now: datetime) -> str:
        return now.strftime("%I:%M %p").lstrip("0")

    def _calc(self, intent: router.Intent, make) -> Reply:
        try:
            value = calc.evaluate(intent.args["expression"])
            return make(f"{intent.args['expression']} = {calc.format_number(value)}")
        except calc.CalcError as exc:
            return make(str(exc))

    @staticmethod
    def _notes(notes, empty: str, make) -> Reply:
        if not notes:
            return make(empty)
        lines = [f"#{n.id}: {n.text}" for n in notes]
        return make("Your notes:\n" + "\n".join(lines), data={"count": len(notes)})

    def _tasks(self, make) -> Reply:
        tasks = self._store.list_tasks()
        if not tasks:
            return make("You have no open tasks.")
        lines = [f"#{t.id}: {t.title}" for t in tasks]
        return make("Your open tasks:\n" + "\n".join(lines), data={"count": len(tasks)})

    def _task_done(self, task_id: int, make) -> Reply:
        existing = self._store.get_task(task_id)
        if existing is None:
            return make(f"I couldn't find task #{task_id}.")
        if existing.done:
            return make(f"Task #{task_id} was already done.")
        done = self._store.complete_task(task_id)
        if done is None:
            return make(f"I couldn't update task #{task_id}.")
        return make(f"Marked task #{task_id} as done: {done.title}")

    def _reminders(self, make) -> Reply:
        items = self._store.list_reminders()
        if not items:
            return make("You have no upcoming reminders.")
        lines = [
            f"#{r.id}: {r.title} — {self._format_when(parse_iso(r.due_at))}" for r in items
        ]
        return make("Your reminders (saved in Aven):\n" + "\n".join(lines), data={"count": len(items)})

    def _format_when(self, moment: datetime) -> str:
        local = moment.astimezone(self._clock().tzinfo)
        return f"{local.strftime('%A')} {local.day} {local.strftime('%B')} at {self._clock_time(local)}"

    def _reminder_add(self, text: str, conv: str, language: str, now: datetime) -> Reply:
        parsed = timeparse.parse_reminder_request(text, now)
        if parsed.kind == "invalid":
            return Reply(
                "I couldn't understand that time. Try something like “at 7 pm” or “in 10 minutes”.",
                "reminder_add", conv, language,
            )
        if parsed.kind == "none":
            self._pending[conv] = _Pending(
                "reminder_when", now + PENDING_TTL, {"title": parsed.title}
            )
            what = f" to {parsed.title}" if parsed.title else ""
            return Reply(
                f"When should I remind you{what}?", "reminder_add", conv, language,
                needs_input="clarification",
            )
        return self._schedule(parsed, conv, language, now)

    def _schedule(
        self, parsed: timeparse.ReminderParse, conv: str, language: str, now: datetime
    ) -> Reply:
        if parsed.needs_meridiem:
            self._pending[conv] = _Pending(
                "reminder_meridiem", now + PENDING_TTL,
                {"title": parsed.title, "parse": parsed},
            )
            clock = f"{parsed.hour}:{parsed.minute:02d}"
            return Reply(
                f"Do you mean {clock} AM or {clock} PM?", "reminder_add", conv, language,
                needs_input="clarification",
            )
        return self._finish_absolute(parsed, parsed.title, None, conv, language, now)

    def _finish_absolute(
        self, parsed: timeparse.ReminderParse, title: str, meridiem: str | None,
        conv: str, language: str, now: datetime,
    ) -> Reply:
        due = timeparse.build_due(parsed, now, meridiem)
        if due <= now:
            self._pending[conv] = _Pending(
                "reminder_when", now + PENDING_TTL, {"title": title}
            )
            return Reply(
                "That time has already passed. When should I remind you?",
                "reminder_add", conv, language, needs_input="clarification",
            )
        reminder = self._store.add_reminder(title, due)
        what = f" to {title.strip()}" if title.strip() else ""
        return Reply(
            f"Okay, I've saved a reminder{what} for {self._format_when(due)}. "
            "It's stored in Aven only, not in an external calendar.",
            "reminder_add", conv, language, data={"reminder_id": reminder.id},
        )

    # -- device actions ---------------------------------------------------------

    def _open(self, target: str, conv: str, language: str) -> Reply:
        return self._run_action(target, conv, language, confirmed=False)

    def _run_action(self, target: str, conv: str, language: str, confirmed: bool) -> Reply:
        try:
            proposal = self._policy.resolve(target)
        except ActionError as exc:
            return Reply(str(exc), "open", conv, language)
        if proposal.requires_confirmation and not confirmed:
            self._pending[conv] = _Pending(
                "confirm_action", self._clock() + PENDING_TTL, {"target": target}
            )
            return Reply(
                f"Open {proposal.label}? Say yes to confirm or no to cancel.",
                "open", conv, language, needs_input="confirmation",
            )
        return self._execute(proposal, conv, language)

    def _execute(self, proposal: ActionProposal, conv: str, language: str) -> Reply:
        result = self._executor.run(proposal)
        if result.ok:
            return Reply(
                f"I started {proposal.label}. ({result.message})", "open", conv, language,
                data={"action": proposal.kind.value},
            )
        return Reply(
            f"I couldn't open {proposal.label}: {result.message}", "open", conv, language,
            data={"action": proposal.kind.value},
        )


def _with_title(parsed: timeparse.ReminderParse, title: str) -> timeparse.ReminderParse:
    return replace(parsed, title=parsed.title or title)
