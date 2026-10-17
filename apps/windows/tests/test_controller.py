import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controllers.assistant_controller import AssistantController  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.database.store import Store  # noqa: E402


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.controller = AssistantController(Settings(), self.store)

    def test_conversation_id_is_kept_between_messages(self):
        self.controller.send("hello")
        first = self.controller.conversation_id
        self.controller.send("what is 1 + 1")
        self.assertEqual(self.controller.conversation_id, first)
        self.controller.new_conversation()
        self.assertIsNone(self.controller.conversation_id)

    def test_due_reminders_fire_exactly_once(self):
        past = datetime.now().astimezone() - timedelta(minutes=1)
        self.store.add_reminder("stretch", past)
        self.store.add_reminder("later", datetime.now().astimezone() + timedelta(hours=1))
        first = self.controller.poll_due_reminders()
        self.assertEqual([r.title for r in first], ["stretch"])
        self.assertEqual(self.controller.poll_due_reminders(), [])

    def test_clear_history_resets_conversation(self):
        self.controller.send("hello")
        self.assertEqual(self.controller.clear_history(), 1)
        self.assertIsNone(self.controller.conversation_id)

    def test_status_labels_do_not_overclaim(self):
        self.assertIn("Offline", self.controller.mode_label)
        self.assertIn("not set up", self.controller.voice_label)


if __name__ == "__main__":
    unittest.main()
