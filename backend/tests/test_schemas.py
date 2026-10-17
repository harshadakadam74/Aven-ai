import unittest

from pydantic import ValidationError

from app.schemas.api import ChatRequest, NoteCreate, TaskCreate


class SchemaTests(unittest.TestCase):
    def test_chat_request_valid(self):
        r = ChatRequest(message="  hello  ", conversation_id="abc_123-X")
        self.assertEqual(r.message, "hello")
        self.assertFalse(r.private)

    def test_chat_request_rejects_bad_input(self):
        for kwargs in [
            {"message": ""}, {"message": "   "}, {"message": "x" * 2001},
            {"message": "hi", "conversation_id": "../etc"}, {"message": "hi", "conversation_id": "a" * 65},
            {"message": "hi", "run": "rm -rf /"},  # unknown fields are rejected
        ]:
            with self.assertRaises(ValidationError, msg=kwargs):
                ChatRequest(**kwargs)

    def test_task_and_note(self):
        self.assertEqual(TaskCreate(title=" buy milk ").title, "buy milk")
        with self.assertRaises(ValidationError):
            TaskCreate(title="bad\x00title")
        with self.assertRaises(ValidationError):
            TaskCreate(title="x" * 201)
        with self.assertRaises(ValidationError):
            NoteCreate(text="")


if __name__ == "__main__":
    unittest.main()
