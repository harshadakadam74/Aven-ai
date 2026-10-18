import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from app.automation.actions import ActionError
from app.core.config import Settings
from controllers.windows_action_service import WindowsActionService


class WindowsActionServiceTests(unittest.TestCase):
    def make_service(self, data):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        config = Path(temp.name) / "windows_actions.json"
        config.write_text(json.dumps(data), encoding="utf-8")
        return WindowsActionService(Settings(), config)

    def test_registry_lists_supported_actions_and_resolves_configured_app(self):
        service = self.make_service({"applications": {"python test app": sys.executable}})
        self.assertIn("chrome", service.supported_actions)
        self.assertIn("projects", service.supported_actions)
        proposal = service.resolve("python test app")
        self.assertEqual(proposal.argv[0], sys.executable)

    def test_missing_executable_is_reported_before_launch(self):
        service = self.make_service({"applications": {"ghost": "Z:\\missing\\ghost.exe"}})
        with self.assertRaisesRegex(ActionError, "isn't installed|isn't available"):
            service.resolve("ghost")

    def test_shell_like_or_unregistered_target_is_denied(self):
        service = self.make_service({})
        for target in ("powershell", "notepad && del *", "cmd.exe /c calc"):
            with self.assertRaises(ActionError):
                service.resolve(target)

    def test_configured_project_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "AvenProject").mkdir()
            service = self.make_service({"approved_directories": [str(root)]})
            proposal = service.resolve("AvenProject project")
            self.assertEqual(Path(proposal.path), root / "AvenProject")
            with self.assertRaises(ActionError):
                service.resolve("..\\Windows folder")

    def test_invalid_config_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            self.make_service({"applications": []})


if __name__ == "__main__":
    unittest.main()