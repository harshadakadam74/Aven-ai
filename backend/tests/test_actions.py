import os
import sys
import tempfile
import unittest
from pathlib import Path

from app.automation.actions import (
    ActionError, ActionKind, AutomationPolicy, ExecutionResult, SystemExecutor, default_apps,
)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "Scriptora").mkdir()
        (self.root / "docs").mkdir()
        self.outside = Path(tempfile.mkdtemp())
        self.policy = AutomationPolicy(
            approved_dirs=(self.root,), extra_apps={"pytool": sys.executable}, platform="linux"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowlisted_app_resolves_to_fixed_argv(self):
        p = self.policy.resolve("PyTool")
        self.assertEqual((p.kind, p.argv), (ActionKind.OPEN_APP, (sys.executable,)))

    def test_unknown_or_shell_like_apps_are_refused(self):
        for target in ["cmd", "powershell", "notepad && del *", "rm -rf /", "cmd.exe /c calc", ""]:
            with self.assertRaises(ActionError, msg=target):
                self.policy.resolve(target)

    def test_missing_executable_is_reported(self):
        p = AutomationPolicy(extra_apps={"ghost": "/no/such/program"}, platform="linux")
        with self.assertRaises(ActionError):
            p.resolve("ghost")

    def test_windows_defaults_only_on_windows(self):
        self.assertIn("notepad", default_apps("win32"))
        self.assertNotIn("notepad", default_apps("linux"))

    def test_project_and_folder_resolution(self):
        p = self.policy.resolve("my scriptora project".replace("my ", ""))
        self.assertEqual(Path(p.path), self.root / "Scriptora")
        p = self.policy.resolve("docs folder")
        self.assertEqual((p.kind, Path(p.path)), (ActionKind.OPEN_FOLDER, self.root / "docs"))

    def test_path_traversal_is_blocked(self):
        for target in ["../etc folder", "..\\windows folder", "a/b folder", "/etc project", "folder .."]:
            with self.assertRaises(ActionError, msg=target):
                self.policy.resolve(target)

    def test_symlink_escape_is_blocked(self):
        link = self.root / "sneaky"
        try:
            os.symlink(self.outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ActionError):
            self.policy.resolve("sneaky folder")

    def test_unknown_project_asks_user_to_configure(self):
        with self.assertRaises(ActionError) as ctx:
            self.policy.resolve("nothing project")
        self.assertIn("AVEN_AI_APPROVED_DIRS", str(ctx.exception))
        with self.assertRaises(ActionError) as ctx:
            AutomationPolicy().resolve("anything project")
        self.assertIn("No folders are approved", str(ctx.exception))

    def test_urls(self):
        self.assertEqual(self.policy.resolve("example.com").url, "https://example.com")
        self.assertEqual(self.policy.resolve("https://example.com/a?b=1").kind, ActionKind.OPEN_URL)
        for bad in ["javascript:alert(1)", "file:///etc/passwd", "https://user:pw@example.com", "https://exa mple.com"]:
            with self.assertRaises(ActionError, msg=bad):
                self.policy.resolve(bad)

    def test_confirmation_flag(self):
        p = AutomationPolicy(extra_apps={"pytool": sys.executable}, confirm_actions=True)
        self.assertTrue(p.resolve("pytool").requires_confirmation)
        self.assertFalse(self.policy.resolve("pytool").requires_confirmation)


class ExecutorTests(unittest.TestCase):
    """Uses the Python interpreter itself as a harmless launch target."""

    def test_launch_safe_target(self):
        policy = AutomationPolicy(extra_apps={"pytool": sys.executable})
        result = SystemExecutor().run(policy.resolve("pytool"))
        self.assertTrue(result.ok, result.message)

    def test_failed_launch_is_reported_as_failure(self):
        policy = AutomationPolicy(extra_apps={"falsy": "/bin/false"})
        if not Path("/bin/false").exists():
            self.skipTest("/bin/false unavailable")
        result = SystemExecutor().run(policy.resolve("falsy"))
        self.assertFalse(result.ok)

    def test_vanished_folder_does_not_crash_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposal = AutomationPolicy(approved_dirs=(Path(tmp).parent,)).resolve(f"{Path(tmp).name} folder")
        # Directory is gone by now; the executor must return a result, not raise.
        result = SystemExecutor().run(proposal)
        self.assertIsInstance(result, ExecutionResult)


if __name__ == "__main__":
    unittest.main()
