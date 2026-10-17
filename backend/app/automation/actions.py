"""Typed, allowlisted device actions.

Flow for every action: the assistant turns a request into an ``ActionProposal``
(``AutomationPolicy.resolve`` validates the target against the allowlist and the
approved folders), optionally asks for confirmation, then hands the proposal to
an ``Executor``. Nothing here accepts shell text, scripts or free-form commands:
apps are launched from fixed argument lists with ``shell=False``.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

log = logging.getLogger("aven.automation")

_LAUNCH_WAIT_SECONDS = 1.0
_DOMAIN = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:[/?#]\S*)?$", re.IGNORECASE)
_SAFE_NAME = re.compile(r"^[\w][\w .\-]*$", re.UNICODE)


class ActionKind(str, Enum):
    OPEN_APP = "open_app"
    OPEN_PROJECT = "open_project"
    OPEN_FOLDER = "open_folder"
    OPEN_URL = "open_url"


class ActionError(Exception):
    """The request can't be turned into a safe action. The message is user-safe."""


@dataclass(frozen=True)
class AppSpec:
    command: str
    ok_codes: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class ActionProposal:
    kind: ActionKind
    label: str  # human description, e.g. "Notepad"
    target: str  # what the user asked for (used to re-validate after confirmation)
    argv: tuple[str, ...] = ()
    path: str | None = None
    url: str | None = None
    ok_codes: tuple[int, ...] = (0,)
    requires_confirmation: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    message: str


class Executor(Protocol):
    def run(self, proposal: ActionProposal) -> ExecutionResult: ...


def default_apps(platform: str | None = None) -> dict[str, AppSpec]:
    platform = platform or sys.platform
    apps: dict[str, AppSpec] = {
        "vscode": AppSpec("code"),
        "vs code": AppSpec("code"),
        "visual studio code": AppSpec("code"),
    }
    if platform.startswith("win"):
        apps.update(
            {
                "notepad": AppSpec("notepad.exe"),
                "calculator": AppSpec("calc.exe"),
                "calc": AppSpec("calc.exe"),
                "paint": AppSpec("mspaint.exe"),
                "file explorer": AppSpec("explorer.exe", ok_codes=(0, 1)),
                "explorer": AppSpec("explorer.exe", ok_codes=(0, 1)),
            }
        )
    return apps


class AutomationPolicy:
    def __init__(
        self,
        approved_dirs: tuple[Path, ...] = (),
        extra_apps: dict[str, str] | None = None,
        confirm_actions: bool = False,
        platform: str | None = None,
    ) -> None:
        self._apps = default_apps(platform)
        for alias, path in (extra_apps or {}).items():
            self._apps[alias.lower()] = AppSpec(path)
        self._dirs = tuple(Path(d).expanduser() for d in approved_dirs)
        self._confirm = confirm_actions

    # -- public -----------------------------------------------------------------

    def resolve(self, target: str) -> ActionProposal:
        text = target.strip()
        if not text or len(text) > 200 or any(ord(ch) < 32 for ch in text):
            raise ActionError("I didn't understand what you want me to open.")
        low = text.lower()

        url = self._as_url(text)
        if url:
            return ActionProposal(
                ActionKind.OPEN_URL, url, text, url=url, requires_confirmation=self._confirm
            )

        project = re.fullmatch(r"(?:project\s+(.+)|(.+?)\s+project)", low)
        if project:
            return self._project(project.group(1) or project.group(2), text)
        folder = re.fullmatch(r"(?:folder\s+(.+)|(.+?)\s+folder)", low)
        if folder:
            return self._folder(folder.group(1) or folder.group(2), text)

        spec = self._apps.get(low)
        if spec is None:
            raise ActionError(
                f"“{text}” isn't one of my approved apps. "
                "You can add one with AVEN_AI_EXTRA_APPS."
            )
        executable = shutil.which(spec.command)
        if executable is None:
            raise ActionError(f"{text} isn't installed or isn't available on this computer.")
        return ActionProposal(
            ActionKind.OPEN_APP, text.title(), text, argv=(executable,),
            ok_codes=spec.ok_codes, requires_confirmation=self._confirm,
        )

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _as_url(text: str) -> str | None:
        low = text.lower()
        if low.startswith(("http://", "https://")):
            candidate = text
        elif _DOMAIN.match(text):
            candidate = "https://" + text
        else:
            return None
        if re.search(r"\s", candidate):
            raise ActionError("That web address contains spaces, so I won't open it.")
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
            raise ActionError("That doesn't look like a valid web address.")
        if "@" in parsed.netloc:
            raise ActionError("I won't open web addresses that contain a username or password.")
        return candidate

    def _find_directory(self, name: str, what: str) -> Path:
        if not self._dirs:
            raise ActionError(
                "No folders are approved yet. Set AVEN_AI_APPROVED_DIRS to the folders "
                "I'm allowed to open."
            )
        name = name.strip()
        if not _SAFE_NAME.match(name) or ".." in name:
            raise ActionError(f"“{name}” isn't a valid {what} name.")
        for root in self._dirs:
            try:
                resolved_root = root.resolve()
                children = list(resolved_root.iterdir())
            except OSError:
                continue
            for child in children:
                if child.name.casefold() != name.casefold():
                    continue
                try:
                    resolved = child.resolve(strict=True)
                except OSError:
                    continue
                if resolved.is_dir() and resolved.is_relative_to(resolved_root):
                    return resolved
        raise ActionError(
            f"I couldn't find a {what} called “{name}” in your approved folders. "
            "Check the name or add its parent folder to AVEN_AI_APPROVED_DIRS."
        )

    def _folder(self, name: str, original: str) -> ActionProposal:
        path = self._find_directory(name, "folder")
        return ActionProposal(
            ActionKind.OPEN_FOLDER, f"folder {path.name}", original, path=str(path),
            requires_confirmation=self._confirm,
        )

    def _project(self, name: str, original: str) -> ActionProposal:
        path = self._find_directory(name, "project")
        editor = shutil.which("code")
        if editor:
            return ActionProposal(
                ActionKind.OPEN_PROJECT, f"project {path.name} in VS Code", original,
                argv=(editor, str(path)), path=str(path), requires_confirmation=self._confirm,
            )
        return ActionProposal(
            ActionKind.OPEN_FOLDER, f"project folder {path.name}", original, path=str(path),
            requires_confirmation=self._confirm,
        )


class SystemExecutor:
    """Runs validated proposals on this computer.

    "Success" means the operating system accepted the request (the process
    started and did not fail immediately, or the shell handler was invoked). It
    cannot prove that a window is visible, and replies are worded accordingly.
    """

    def run(self, proposal: ActionProposal) -> ExecutionResult:
        log.info("Executing action kind=%s", proposal.kind.value)  # no paths or transcripts
        try:
            if proposal.kind in (ActionKind.OPEN_APP, ActionKind.OPEN_PROJECT):
                return self._spawn(list(proposal.argv), proposal.ok_codes)
            if proposal.kind is ActionKind.OPEN_FOLDER and proposal.path:
                return self._open_path(proposal.path)
            if proposal.kind is ActionKind.OPEN_URL and proposal.url:
                opened = webbrowser.open(proposal.url, new=2)
                if opened:
                    return ExecutionResult(True, "Asked your browser to open the page.")
                return ExecutionResult(False, "No web browser accepted the request.")
        except Exception:  # noqa: BLE001 - report any launcher failure truthfully
            log.exception("Action failed kind=%s", proposal.kind.value)
            return ExecutionResult(False, "The system refused or failed to run that.")
        return ExecutionResult(False, "That action isn't supported.")

    @staticmethod
    def _spawn(argv: list[str], ok_codes: tuple[int, ...]) -> ExecutionResult:
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            close_fds=True,
        )
        try:
            code = proc.wait(timeout=_LAUNCH_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            return ExecutionResult(True, "Started.")
        if code in ok_codes:
            return ExecutionResult(True, "Started.")
        return ExecutionResult(False, f"It exited right away with code {code}.")

    def _open_path(self, path: str) -> ExecutionResult:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]  # Windows only
            return ExecutionResult(True, "Asked Windows to open the folder.")
        opener = shutil.which("xdg-open") or shutil.which("open")
        if opener is None:
            return ExecutionResult(False, "No folder opener is available on this system.")
        return self._spawn([opener, path], (0,))
