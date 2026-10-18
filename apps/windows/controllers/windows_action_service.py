"""Windows action registry backed by the shared safe automation policy."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

from app.automation.actions import ActionError, AppSpec, AutomationPolicy, SystemExecutor, default_apps
from app.core.config import Settings

log = logging.getLogger("aven.windows.actions")
_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "windows_actions.json"
_SUPPORTED = {
    "chrome": "Open Google Chrome",
    "notepad": "Open Notepad",
    "calculator": "Open Calculator",
    "vscode": "Open Visual Studio Code",
    "paint": "Open Paint",
    "file explorer": "Open File Explorer",
    "folders": "Open configured folders",
    "projects": "Open configured project directories",
    "web addresses": "Open validated HTTP or HTTPS URLs",
}


class WindowsActionService:
    """Registry of supported app and approved-directory actions; never runs shell text."""

    def __init__(self, settings: Settings, config_path: Path | None = None) -> None:
        config = self._load_config(config_path or _CONFIG_PATH)
        apps = default_apps("win32" if sys.platform.startswith("win") else sys.platform)
        if sys.platform.startswith("win"):
            apps.update({"chrome": AppSpec(self._chrome_path() or "chrome.exe")})

        configured_apps = dict(settings.extra_apps)
        configured_apps.update(self._configured_apps(config.get("applications", {})))
        configured_dirs = list(settings.approved_dirs)
        configured_dirs.extend(self._configured_dirs(config.get("approved_directories", [])))
        for alias in configured_apps:
            apps[alias.lower()] = AppSpec(configured_apps[alias])

        self.policy = AutomationPolicy(
            approved_dirs=tuple(configured_dirs),
            extra_apps={alias: spec.command for alias, spec in apps.items()},
            confirm_actions=settings.confirm_actions,
        )
        self.executor = SystemExecutor()
        self.supported_actions = dict(_SUPPORTED)
        self.supported_actions.update({alias: f"Launch configured app: {alias}" for alias in configured_apps})

    @staticmethod
    def _load_config(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            log.info("Windows action config not found; using built-in actions")
            return {}
        except (OSError, json.JSONDecodeError):
            log.exception("Could not read Windows action config")
            return {}
        if not isinstance(data, dict):
            raise ValueError("windows_actions.json must contain a JSON object")
        if not isinstance(data.get("applications", {}), dict):
            raise ValueError("applications in windows_actions.json must be an object")
        if not isinstance(data.get("approved_directories", []), list):
            raise ValueError("approved_directories in windows_actions.json must be a list")
        return data

    @staticmethod
    def _configured_apps(apps: dict) -> dict[str, str]:
        result = {}
        for alias, executable in apps.items():
            if (
                not isinstance(alias, str)
                or not alias.strip()
                or not isinstance(executable, str)
                or not executable.strip()
            ):
                raise ValueError("Each configured application needs a name and executable path")
            result[alias.strip().lower()] = executable.strip()
        return result

    @staticmethod
    def _configured_dirs(directories: list) -> list[Path]:
        if any(not isinstance(item, str) or not item.strip() for item in directories):
            raise ValueError("Each approved directory must be a non-empty path string")
        return [Path(os.path.expandvars(item)).expanduser() for item in directories]

    @staticmethod
    def _chrome_path() -> str | None:
        found = shutil.which("chrome.exe")
        if found:
            return found
        candidates = (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Google/Chrome/Application/chrome.exe",
        )
        return next((str(path) for path in candidates if path.is_file()), None)

    def resolve(self, target: str):
        return self.policy.resolve(target)

    def run(self, proposal):
        return self.executor.run(proposal)