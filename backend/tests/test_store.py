import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database.store import SCHEMA_VERSION, Store, StoreError

UTC = timezone.utc


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_health_and_schema_version(self):
        self.assertEqual(self.store.health(), {"ok": True, "schema_version": SCHEMA_VERSION})

    def test_notes_roundtrip_and_search_escaping(self):
        self.store.add_note("buy milk")
        self.store.add_note("100% done_task")
        self.assertEqual([n.text for n in self.store.list_notes()], ["100% done_task", "buy milk"])
        self.assertEqual(len(self.store.search_notes("milk")), 1)
        self.assertEqual(len(self.store.search_notes("%")), 1)  # literal %, not a wildcard
        self.assertEqual(len(self.store.search_notes("_")), 1)
        self.assertEqual(self.store.search_notes("x'; DROP TABLE notes;--"), [])
        self.assertEqual(len(self.store.list_notes()), 2)
        with self.assertRaises(ValueError):
            self.store.add_note("   ")

    def test_tasks(self):
        a = self.store.add_task("first")
        b = self.store.add_task("second")
        self.assertEqual([t.title for t in self.store.list_tasks()], ["first", "second"])
        done = self.store.complete_task(a.id)
        self.assertTrue(done.done and done.completed_at)
        self.assertIsNone(self.store.complete_task(a.id))  # already done
        self.assertIsNone(self.store.complete_task(999))
        self.assertEqual([t.id for t in self.store.list_tasks()], [b.id])
        self.assertEqual(len(self.store.list_tasks(include_done=True)), 2)

    def test_reminders_due_and_fired(self):
        now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
        soon = self.store.add_reminder("soon", now + timedelta(minutes=5))
        self.store.add_reminder("later", now + timedelta(hours=2))
        self.assertEqual(self.store.due_reminders(now), [])
        due = self.store.due_reminders(now + timedelta(minutes=6))
        self.assertEqual([r.id for r in due], [soon.id])
        self.assertTrue(self.store.mark_reminder_fired(soon.id))
        self.assertFalse(self.store.mark_reminder_fired(soon.id))  # no duplicate firing
        self.assertEqual(self.store.due_reminders(now + timedelta(minutes=6)), [])
        self.assertEqual(len(self.store.list_reminders("fired")), 1)

    def test_reminders_require_aware_datetimes(self):
        with self.assertRaises(ValueError):
            self.store.add_reminder("x", datetime(2026, 1, 1, 12, 0))

    def test_conversations_and_history_deletion(self):
        cid = self.store.new_conversation_id()
        self.store.add_message(cid, "user", "hi", "en")
        self.store.add_message(cid, "assistant", "hello", "en")
        self.assertEqual([m.role for m in self.store.recent_messages(cid)], ["user", "assistant"])
        self.assertEqual(self.store.delete_all_history(), 1)
        self.assertEqual(self.store.recent_messages(cid), [])
        with self.assertRaises(ValueError):
            self.store.ensure_conversation("../bad id")

    def test_settings(self):
        self.assertIsNone(self.store.get_setting("voice"))
        self.store.set_setting("voice", "female")
        self.store.set_setting("voice", "male")
        self.assertEqual(self.store.get_setting("voice"), "male")


class StoreFileTests(unittest.TestCase):
    def test_persists_across_reopen_and_migrations_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "aven.db"
            s = Store(path)
            s.add_note("kept")
            s.close()
            s = Store(path)
            self.assertEqual([n.text for n in s.list_notes()], ["kept"])
            s.close()

    def test_corrupt_database_is_moved_aside_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aven.db"
            path.write_bytes(b"this is definitely not a sqlite database" * 50)
            s = Store(path)
            s.add_note("fresh start works")
            s.close()
            backups = list(Path(tmp).glob("aven.db.corrupt-*"))
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].read_bytes().startswith(b"this is definitely"))

    def test_newer_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aven.db"
            conn = sqlite3.connect(path)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
            conn.close()
            with self.assertRaises(StoreError):
                Store(path)


if __name__ == "__main__":
    unittest.main()
