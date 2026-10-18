"""Qt-free controller: builds the assistant and exposes plain methods to the UI.

Keeping this free of PySide6 means it can be unit-tested anywhere. The window
calls ``send`` from a worker thread and ``poll_due_reminders`` from a timer.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import Settings, configure_logging  # noqa: E402
from app.database.store import Store, parse_iso  # noqa: E402
from app.services.assistant import AssistantService, Reply  # noqa: E402
from app.services.ai_provider import provider_status  # noqa: E402
from controllers.windows_action_service import WindowsActionService  # noqa: E402

log = logging.getLogger("aven.windows")


@dataclass(frozen=True)
class DueReminder:
    id: int
    title: str


class AssistantController:
    def __init__(self, settings: Settings | None = None, store: Store | None = None) -> None:
        self.settings = settings or Settings.from_env()
        configure_logging(self.settings.log_level)
        self._owns_store = store is None
        self.store = store or Store(self.settings.database_path)
        self.action_service = WindowsActionService(self.settings)
        self.assistant = AssistantService(
            self.store,
            self.settings,
            executor=self.action_service.executor,
            policy=self.action_service.policy,
        )
        self.conversation_id: str | None = None

    # Status shown in the dashboard. Only things that actually exist in Stage 1.
    @property
    def mode_label(self) -> str:
        return f"Online AI: {provider_status(self.settings)}"

    @property
    def ai_status(self) -> str:
        return provider_status(self.settings)

    @property
    def voice_label(self) -> str:
        return "Offline speech engines are checked in the Windows diagnostics screen"

    def send(self, text: str, private: bool = False) -> Reply:
        reply = self.assistant.handle_text(text, self.conversation_id, private)
        self.conversation_id = reply.conversation_id
        return reply

    def new_conversation(self) -> None:
        self.conversation_id = None

    def poll_due_reminders(self) -> list[DueReminder]:
        """Return reminders that just became due and mark them fired (once)."""
        now = datetime.now().astimezone()
        fired: list[DueReminder] = []
        for reminder in self.store.due_reminders(now):
            if self.store.mark_reminder_fired(reminder.id):
                fired.append(DueReminder(reminder.id, reminder.title))
                log.info("Reminder %d fired (due %s)", reminder.id, parse_iso(reminder.due_at).isoformat())
        return fired

    def clear_history(self) -> int:
        count = self.store.delete_all_history()
        self.conversation_id = None
        return count

    def close(self) -> None:
        if self._owns_store:
            self.store.close()
