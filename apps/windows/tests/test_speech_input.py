import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.speech_input import _validate_language  # noqa: E402


class SpeechInputTests(unittest.TestCase):
    def test_accepts_supported_language_with_confidence(self):
        self.assertEqual(_validate_language("mr", 0.8), "mr")

    def test_rejects_unsupported_language(self):
        with self.assertRaisesRegex(RuntimeError, "English, Hindi, or Marathi"):
            _validate_language("ro", 0.9)

    def test_rejects_low_confidence_language(self):
        with self.assertRaisesRegex(RuntimeError, "couldn't confidently detect"):
            _validate_language("hi", 0.12)


if __name__ == "__main__":
    unittest.main()