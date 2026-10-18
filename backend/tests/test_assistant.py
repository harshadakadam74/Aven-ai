import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.automation.actions import ActionProposal, AutomationPolicy, ExecutionResult
from app.core.config import Settings
from app.database.store import Store
from app.services.assistant import MAX_MESSAGE_LENGTH, AssistantService
from app.services.ai_provider import ProviderError

IST = timezone(timedelta(hours=5, minutes=30))


class FakeExecutor:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls: list[ActionProposal] = []

    def run(self, proposal):
        self.calls.append(proposal)
        return ExecutionResult(self.ok, "Started." if self.ok else "boom")


class FakeAIProvider:
    def __init__(self, response="A concise online answer."):
        self.response = response
        self.calls = []

    def generate(self, text, language):
        self.calls.append((text, language))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Base(unittest.TestCase):
    def make(self, settings=None, executor=None, policy=None, now=None):
        self.now = now or datetime(2026, 10, 17, 15, 0, tzinfo=IST)  # Saturday 3:00 PM
        self.store = Store(":memory:")
        self.executor = executor or FakeExecutor()
        self.svc = AssistantService(
            self.store, settings or Settings(), self.executor, policy, clock=lambda: self.now
        )
        self.addCleanup(self.store.close)
        return self.svc


class ChatBasics(Base):
    def test_greetings_vary_and_wake_phrase_is_handled(self):
        svc = self.make()
        first = svc.handle_text("Hey Aven")
        second = svc.handle_text("hello", first.conversation_id)
        self.assertEqual(first.text, "Hey! I'm here. What can I do for you?")
        self.assertNotEqual(first.text, second.text)

    def test_marathi_and_hindi_replies(self):
        svc = self.make()
        mr = svc.handle_text("Hey Aven, kasa ahes?")
        self.assertEqual((mr.language, mr.intent), ("mr", "how_are_you"))
        self.assertIn("मी तयार आहे", mr.text)
        hi = svc.handle_text("आप कैसे हैं")
        self.assertEqual(hi.language, "hi")
        self.assertIn("आप कैसे हैं", hi.text)
        self.assertNotIn("खुश", hi.text)  # no claimed feelings

    def test_time_date_calc(self):
        svc = self.make()
        self.assertEqual(svc.handle_text("what time is it").text, "It's 3:00 PM.")
        self.assertEqual(svc.handle_text("what's the date").text, "Today is Saturday, 17 October 2026.")
        self.assertEqual(svc.handle_text("what is 12 times 5").text, "12 * 5 = 60")
        self.assertIn("divide by zero", svc.handle_text("5 / 0").text)

    def test_unknown_gets_honest_offline_reply_not_silence(self):
        reply = self.make().handle_text("explain python decorators")
        self.assertEqual(reply.intent, "unknown")
        self.assertIn("can't answer that offline", reply.text)

    def test_stop_signals_speech_interruption(self):
        reply = self.make().handle_text("stop")
        self.assertTrue(reply.stop_speaking)

    def test_online_provider_handles_only_unknown_intents(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        provider = FakeAIProvider()
        service = AssistantService(store, Settings(), ai_provider=provider)
        self.assertEqual(service.handle_text("what is 2 + 2").text, "2 + 2 = 4")
        self.assertEqual(service.handle_text("explain decorators").text, provider.response)
        self.assertEqual(provider.calls, [("explain decorators", "en")])

    def test_provider_failure_uses_honest_offline_fallback(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        provider = FakeAIProvider(ProviderError("Online AI could not be reached."))
        service = AssistantService(store, Settings(), ai_provider=provider)
        self.assertIn("can't answer that offline", service.handle_text("explain decorators").text)

    def test_empty_and_overlong_messages(self):
        svc = self.make()
        self.assertEqual(svc.handle_text("   ").intent, "empty")
        self.assertEqual(svc.handle_text("a" * (MAX_MESSAGE_LENGTH + 1)).intent, "error")

    def test_bad_conversation_id_is_replaced(self):
        reply = self.make().handle_text("hi", "../../etc/passwd")
        self.assertRegex(reply.conversation_id, r"^[0-9a-f]{32}$")


class History(Base):
    def test_history_saved_unless_private_or_disabled(self):
        svc = self.make()
        r = svc.handle_text("hello")
        self.assertEqual(len(self.store.recent_messages(r.conversation_id)), 2)
        p = svc.handle_text("hello", private=True)
        self.assertEqual(self.store.recent_messages(p.conversation_id), [])
        svc2 = self.make(Settings(store_history=False))
        r2 = svc2.handle_text("hello")
        self.assertEqual(self.store.recent_messages(r2.conversation_id), [])

    def test_storage_failure_does_not_break_reply(self):
        svc = self.make()
        self.store.close()
        self.store = Store(":memory:")  # fresh store for cleanup
        svc._store.add_message = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
        with self.assertLogs("aven.assistant", level="ERROR"):
            reply = svc.handle_text("what is 2 + 2")
        self.assertEqual(reply.text, "2 + 2 = 4")


class Productivity(Base):
    def test_notes(self):
        svc = self.make()
        self.assertIn("don't have any notes", svc.handle_text("show my notes").text)
        self.assertIn("Saved note #1: buy milk", svc.handle_text("take a note buy milk").text)
        self.assertIn("buy milk", svc.handle_text("notes").text)
        self.assertIn("buy milk", svc.handle_text("search notes for milk").text)
        self.assertIn("couldn't find", svc.handle_text("search notes for zebra").text)

    def test_tasks(self):
        svc = self.make()
        self.assertIn("no open tasks", svc.handle_text("list tasks").text)
        svc.handle_text("add task call mom")
        svc.handle_text("add task pay rent")
        self.assertIn("#1: call mom", svc.handle_text("my tasks").text)
        self.assertIn("Marked task #1", svc.handle_text("complete task 1").text)
        self.assertIn("already done", svc.handle_text("complete task 1").text)
        self.assertIn("couldn't find task #9", svc.handle_text("done with 9").text)
        self.assertNotIn("call mom", svc.handle_text("list tasks").text)

    def test_reminder_with_unambiguous_time_is_saved_locally(self):
        svc = self.make()
        reply = svc.handle_text("remind me to call Rahul at 6:30 pm")
        self.assertIn("saved a reminder to call Rahul for Saturday 17 October at 6:30 PM", reply.text)
        self.assertIn("not in an external calendar", reply.text)
        reminders = self.store.list_reminders()
        self.assertEqual([r.title for r in reminders], ["call Rahul"])
        self.assertIn("call Rahul", svc.handle_text("show my reminders").text)

    def test_ambiguous_reminder_asks_then_saves(self):
        svc = self.make()
        ask = svc.handle_text("Remind me to study at seven")
        self.assertEqual(ask.needs_input, "clarification")
        self.assertIn("7:00 AM or 7:00 PM", ask.text)
        self.assertEqual(self.store.list_reminders(), [])  # nothing saved yet
        done = svc.handle_text("pm", ask.conversation_id)
        self.assertIn("reminder to study for Saturday 17 October at 7:00 PM", done.text)
        self.assertEqual(len(self.store.list_reminders()), 1)

    def test_unclear_meridiem_answer_asks_again_and_cancel_drops(self):
        svc = self.make()
        ask = svc.handle_text("remind me to study at seven")
        again = svc.handle_text("hmm", ask.conversation_id)
        self.assertEqual(again.text, "Please answer AM or PM.")
        cancel = svc.handle_text("no", ask.conversation_id)
        self.assertEqual(cancel.intent, "reminder_cancelled")
        self.assertEqual(self.store.list_reminders(), [])

    def test_reminder_without_time_asks_when(self):
        svc = self.make()
        ask = svc.handle_text("remind me to buy milk")
        self.assertIn("When should I remind you to buy milk?", ask.text)
        done = svc.handle_text("in 20 minutes", ask.conversation_id)
        self.assertIn("buy milk", done.text)
        due = self.store.list_reminders()[0]
        self.assertEqual(due.title, "buy milk")
        self.assertEqual(self.store.due_reminders(self.now + timedelta(minutes=21))[0].id, due.id)

    def test_past_time_is_not_saved(self):
        svc = self.make()
        reply = svc.handle_text("remind me to run today at 2 pm")
        self.assertIn("already passed", reply.text)
        self.assertEqual(self.store.list_reminders(), [])

    def test_pending_expires(self):
        svc = self.make()
        ask = svc.handle_text("remind me to study at seven")
        self.now += timedelta(minutes=6)
        reply = svc.handle_text("pm", ask.conversation_id)
        self.assertEqual(reply.intent, "unknown")
        self.assertEqual(self.store.list_reminders(), [])

    def test_unrelated_message_during_pending_is_handled_as_new_command(self):
        svc = self.make()
        ask = svc.handle_text("remind me to study at seven")
        reply = svc.handle_text("what is 2 + 2", ask.conversation_id)
        self.assertEqual(reply.text, "2 + 2 = 4")
        self.assertEqual(self.store.list_reminders(), [])


class Actions(Base):
    def policy(self, **kw):
        return AutomationPolicy(extra_apps={"pytool": sys.executable}, **kw)

    def test_allowlisted_open_runs_and_reports_honestly(self):
        svc = self.make(policy=self.policy())
        reply = svc.handle_text("open pytool")
        self.assertEqual(len(self.executor.calls), 1)
        self.assertIn("I started Pytool", reply.text)

    def test_failed_launch_is_never_reported_as_success(self):
        svc = self.make(executor=FakeExecutor(ok=False), policy=self.policy())
        reply = svc.handle_text("open pytool")
        self.assertIn("couldn't open", reply.text)
        self.assertNotIn("I started", reply.text)

    def test_unapproved_app_is_refused_without_executing(self):
        svc = self.make(policy=self.policy())
        reply = svc.handle_text("open powershell")
        self.assertEqual(self.executor.calls, [])
        self.assertIn("isn't one of my approved apps", reply.text)

    def test_actions_can_be_disabled_for_remote_callers(self):
        self.make(policy=self.policy())
        svc = AssistantService(self.store, Settings(), self.executor, self.policy(),
                               clock=lambda: self.now, allow_actions=False)
        reply = svc.handle_text("open pytool")
        self.assertEqual(self.executor.calls, [])
        self.assertIn("isn't available over this connection", reply.text)

    def test_confirmation_flow_yes_executes_once(self):
        svc = self.make(policy=self.policy(confirm_actions=True))
        ask = svc.handle_text("open pytool")
        self.assertEqual(ask.needs_input, "confirmation")
        self.assertEqual(self.executor.calls, [])
        ok = svc.handle_text("yes", ask.conversation_id)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertIn("I started", ok.text)
        svc.handle_text("yes", ask.conversation_id)  # a stray "yes" must not re-run it
        self.assertEqual(len(self.executor.calls), 1)

    def test_confirmation_flow_no_cancels(self):
        svc = self.make(policy=self.policy(confirm_actions=True))
        ask = svc.handle_text("open pytool")
        no = svc.handle_text("no", ask.conversation_id)
        self.assertEqual(no.intent, "action_cancelled")
        self.assertEqual(self.executor.calls, [])

    def test_project_open_and_unknown_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "Scriptora").mkdir()
            svc = self.make(policy=AutomationPolicy(approved_dirs=(root,)))
            ok = svc.handle_text("Hey Aven, open my Scriptora project")
            self.assertEqual(len(self.executor.calls), 1)
            self.assertIn("Scriptora", ok.text)
            bad = svc.handle_text("open my ghost project")
            self.assertEqual(len(self.executor.calls), 1)
            self.assertIn("AVEN_AI_APPROVED_DIRS", bad.text)


if __name__ == "__main__":
    unittest.main()
