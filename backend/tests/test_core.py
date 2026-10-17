import unittest
from datetime import datetime, timedelta, timezone

from app.core import calc, i18n, router, timeparse
from app.core.config import Settings, database_path_from_url, parse_extra_apps
from app.core.language import detect_language
from app.core.ratelimit import RateLimiter

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 17, 15, 0, tzinfo=IST)  # 3:00 PM


class CalcTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(calc.evaluate("(2 + 3) * 4"), 20)
        self.assertEqual(calc.evaluate("7 / 2"), 3.5)
        self.assertEqual(calc.evaluate("-3 + 5"), 2)

    def test_rejects_unsafe_or_huge(self):
        for bad in ["__import__('os')", "open('x')", "2 ** 1000", "9**9**9", "1/0", "abs(3)", "a+1", "", "(" * 100 + "1" + ")" * 100]:
            with self.assertRaises(calc.CalcError, msg=bad):
                calc.evaluate(bad)

    def test_to_expression(self):
        self.assertEqual(calc.to_expression("what is 12 times 5"), "12 * 5")
        self.assertEqual(calc.to_expression("calculate 10 divided by 4"), "10 / 4")
        self.assertEqual(calc.to_expression("5 x 3"), "5 * 3")
        self.assertEqual(calc.to_expression("2^3"), "2**3")
        self.assertIsNone(calc.to_expression("hello there"))
        self.assertIsNone(calc.to_expression("42"))
        self.assertIsNone(calc.to_expression("__import__('os')"))

    def test_format(self):
        self.assertEqual(calc.format_number(4.0), "4")
        self.assertEqual(calc.format_number(1 / 3), "0.3333333333")


class LanguageTests(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(detect_language("what time is it"), "en")
        self.assertEqual(detect_language("kasa ahes"), "mr")
        self.assertEqual(detect_language("mala kay karaycha ahe"), "mr")
        self.assertEqual(detect_language("mujhe kal ka time bata"), "hinglish")
        self.assertEqual(detect_language("तुम्ही कसे आहात"), "mr")
        self.assertEqual(detect_language("आप कैसे हैं"), "hi")

    def test_devanagari_tie_uses_default(self):
        self.assertEqual(detect_language("नमस्कार", default="mr"), "mr")
        self.assertEqual(detect_language("नमस्कार", default="en"), "hi")


class RouterTests(unittest.TestCase):
    def names(self, text):
        return router.route(text).name

    def test_basic_intents(self):
        cases = {
            "": "empty", "Hey Aven": "greeting", "hello": "greeting", "नमस्कार": "greeting",
            "Hey Aven, kasa ahes?": "how_are_you", "how are you": "how_are_you",
            "what time is it": "time", "किती वाजले": "time",
            "what's the date": "date", "stop": "stop", "थांबा": "stop", "help": "help",
            "take a note buy milk": "note_add", "show my notes": "note_list", "notes": "note_list",
            "search notes for milk": "note_search",
            "add task call mom": "task_add", "list tasks": "task_list", "complete task 3": "task_done",
            "task 2 done": "task_done",
            "remind me to study at seven": "reminder_add", "show my reminders": "reminder_list",
            "what is 12 times 5": "calc", "7+8": "calc",
            "open notepad": "open", "open my scriptora project": "open",
            "tell me a joke": "unknown",
        }
        for text, expected in cases.items():
            self.assertEqual(self.names(text), expected, text)

    def test_args(self):
        self.assertEqual(router.route("Hey Aven, add task to buy milk").args["title"], "buy milk")
        self.assertEqual(router.route("note: call Rahul").args["text"], "call Rahul")
        self.assertEqual(router.route("done with 4").args["id"], 4)
        self.assertEqual(router.route("open my scriptora project").args["target"], "scriptora project")

    def test_notes_word_is_not_a_note_add(self):
        self.assertEqual(self.names("notes about cats"), "unknown")

    def test_yes_no(self):
        for yes in ["yes", "Okay!", "haan", "होय"]:
            self.assertTrue(router.is_yes(yes), yes)
        for no in ["no", "nahi", "नको", "cancel"]:
            self.assertTrue(router.is_no(no), no)
        self.assertFalse(router.is_yes("maybe"))


class TimeParseTests(unittest.TestCase):
    def test_ambiguous_hour_needs_meridiem(self):
        p = timeparse.parse_reminder_request("remind me to study at seven", NOW)
        self.assertEqual((p.kind, p.title, p.hour, p.meridiem), ("absolute", "study", 7, None))
        self.assertTrue(p.needs_meridiem)
        self.assertEqual(timeparse.build_due(p, NOW, "pm"), NOW.replace(hour=19, minute=0))
        # 7 AM already passed today (it is 3 PM) so it rolls to tomorrow.
        self.assertEqual(timeparse.build_due(p, NOW, "am"), NOW.replace(hour=7, minute=0) + timedelta(days=1))

    def test_explicit_markers(self):
        p = timeparse.parse_reminder_request("remind me to call Rahul at 7:30 pm", NOW)
        self.assertEqual((p.title, p.hour, p.minute, p.meridiem), ("call Rahul", 7, 30, "pm"))
        p = timeparse.parse_reminder_request("remind me to run at 18:45", NOW)
        self.assertEqual((p.hour, p.minute, p.meridiem), (18, 45, "24h"))
        p = timeparse.parse_reminder_request("remind me to eat at noon tomorrow", NOW)
        self.assertEqual(timeparse.build_due(p, NOW), NOW.replace(hour=12, minute=0) + timedelta(days=1))

    def test_hint_words_resolve_ampm(self):
        p = timeparse.parse_reminder_request("remind me to read at 9 in the morning", NOW)
        self.assertEqual(p.meridiem, "am")
        self.assertEqual(p.title, "read")
        p = timeparse.parse_reminder_request("remind me to sleep tonight at 10", NOW)
        self.assertEqual(p.meridiem, "pm")

    def test_relative(self):
        p = timeparse.parse_reminder_request("remind me to stretch in 10 minutes", NOW)
        self.assertEqual((p.kind, p.title, p.due), ("relative", "stretch", NOW + timedelta(minutes=10)))
        p = timeparse.parse_reminder_request("remind me to check oven in an hour", NOW)
        self.assertEqual(p.due, NOW + timedelta(hours=1))

    def test_none_and_invalid(self):
        self.assertEqual(timeparse.parse_reminder_request("remind me to buy milk", NOW).kind, "none")
        self.assertEqual(timeparse.parse_reminder_request("remind me to x at 7:75", NOW).kind, "invalid")
        self.assertEqual(timeparse.parse_reminder_request("remind me to x at 14 pm", NOW).kind, "invalid")

    def test_meridiem_replies(self):
        self.assertEqual(timeparse.parse_meridiem("PM"), "pm")
        self.assertEqual(timeparse.parse_meridiem("in the evening"), "pm")
        self.assertEqual(timeparse.parse_meridiem("सकाळ"), "am")
        self.assertIsNone(timeparse.parse_meridiem("whatever"))


class ConfigTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        s = Settings.from_env({})
        self.assertEqual((s.host, s.port, s.database_path, s.api_key), ("127.0.0.1", 8000, "./aven_ai.db", ""))
        self.assertTrue(s.is_loopback)
        s = Settings.from_env({"AVEN_AI_PORT": "9001", "AVEN_AI_CONFIRM_ACTIONS": "yes",
                               "DATABASE_URL": "sqlite:///data/x.db", "AVEN_AI_HOST": "0.0.0.0"})
        self.assertEqual((s.port, s.confirm_actions, s.database_path, s.is_loopback), (9001, True, "data/x.db", False))

    def test_validation(self):
        for env in [{"AVEN_AI_PORT": "abc"}, {"AVEN_AI_PORT": "70000"}, {"DATABASE_URL": "postgres://x"},
                    {"AVEN_AI_CONFIRM_ACTIONS": "maybe"}, {"AVEN_AI_LOG_LEVEL": "LOUD"}, {"AVEN_AI_EXTRA_APPS": "bad"}]:
            with self.assertRaises(ValueError, msg=env):
                Settings.from_env(env)

    def test_api_key_not_in_repr(self):
        self.assertNotIn("secret123", repr(Settings(api_key="secret123")))

    def test_helpers(self):
        self.assertEqual(database_path_from_url("sqlite:///:memory:"), ":memory:")
        self.assertEqual(parse_extra_apps("Tool=C:\\a\\b.exe; x=/usr/bin/x"), {"tool": "C:\\a\\b.exe", "x": "/usr/bin/x"})


class RateLimiterTests(unittest.TestCase):
    def test_window(self):
        t = [0.0]
        rl = RateLimiter(2, 60, clock=lambda: t[0])
        self.assertTrue(rl.allow("a"))
        self.assertTrue(rl.allow("a"))
        self.assertFalse(rl.allow("a"))
        self.assertTrue(rl.allow("b"))
        t[0] = 61
        self.assertTrue(rl.allow("a"))


class I18nTests(unittest.TestCase):
    def test_fallback_and_variants(self):
        self.assertEqual(i18n.text("greeting", "xx"), i18n.text("greeting", "en"))
        self.assertNotEqual(i18n.text("greeting", "en", 0), i18n.text("greeting", "en", 1))
        self.assertEqual(i18n.text("greeting", "en", 3), i18n.text("greeting", "en", 0))


if __name__ == "__main__":
    unittest.main()
