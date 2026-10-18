"""Runtime configuration, read from environment variables only.

No secrets live in source code. ``Settings.from_env`` validates every value
and raises ``ValueError`` with a readable message when something is wrong.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _get_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be true or false")


def _get_int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def database_path_from_url(url: str) -> str:
    """Turn ``sqlite:///./aven_ai.db`` into a filesystem path (or ``:memory:``)."""
    prefix = "sqlite:///"
    if not url.startswith(prefix) or len(url) == len(prefix):
        raise ValueError(
            "DATABASE_URL must look like sqlite:///./aven_ai.db "
            "(only SQLite is supported in Stage 1)"
        )
    return url[len(prefix):]


def parse_extra_apps(raw: str) -> dict[str, str]:
    """Parse ``name=path;name2=path2`` into a dict of lower-cased aliases."""
    apps: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        name, sep, path = part.partition("=")
        name, path = name.strip().lower(), path.strip()
        if not sep or not name or not path:
            raise ValueError("AVEN_AI_EXTRA_APPS entries must look like name=path")
        apps[name] = path
    return apps


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: str = "./aven_ai.db"
    api_key: str = field(default="", repr=False)  # never printed or logged
    ai_provider: str = ""
    ai_api_key: str = field(default="", repr=False)
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 20
    approved_dirs: tuple[Path, ...] = ()
    extra_apps: dict[str, str] = field(default_factory=dict)
    confirm_actions: bool = False
    store_history: bool = True
    log_level: str = "INFO"
    rate_limit_per_minute: int = 60

    @property
    def is_loopback(self) -> bool:
        return self.host in _LOOPBACK_HOSTS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        log_level = env.get("AVEN_AI_LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in logging.getLevelNamesMapping():
            raise ValueError("AVEN_AI_LOG_LEVEL must be a standard logging level")
        dirs_raw = env.get("AVEN_AI_APPROVED_DIRS", "")
        approved = tuple(
            Path(p).expanduser() for p in dirs_raw.split(os.pathsep) if p.strip()
        )
        return cls(
            env=env.get("AVEN_AI_ENV", "development").strip() or "development",
            host=env.get("AVEN_AI_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=_get_int(env, "AVEN_AI_PORT", 8000, 1, 65535),
            database_path=database_path_from_url(
                env.get("DATABASE_URL", "sqlite:///./aven_ai.db").strip()
            ),
            api_key=env.get("AVEN_AI_API_KEY", "").strip(),
            ai_provider=env.get("AI_PROVIDER", "").strip().lower(),
            ai_api_key=env.get("AI_API_KEY", "").strip(),
            ai_model=env.get("AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            ai_base_url=(
                env.get("AI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
                or "https://api.openai.com/v1"
            ),
            ai_timeout_seconds=_get_int(env, "AI_TIMEOUT_SECONDS", 20, 1, 120),
            approved_dirs=approved,
            extra_apps=parse_extra_apps(env.get("AVEN_AI_EXTRA_APPS", "")),
            confirm_actions=_get_bool(env, "AVEN_AI_CONFIRM_ACTIONS", False),
            store_history=_get_bool(env, "AVEN_AI_STORE_HISTORY", True),
            log_level=log_level,
            rate_limit_per_minute=_get_int(env, "AVEN_AI_RATE_LIMIT_PER_MINUTE", 60, 1, 10000),
        )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
