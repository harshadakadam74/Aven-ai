"""SQLite storage for conversations, notes, tasks, reminders and settings.

Stage 1 uses the standard-library ``sqlite3`` driver with parameterized queries
only. Schema changes go through numbered migrations tracked in
``PRAGMA user_version``. A database file that cannot be opened is moved aside
(never deleted) and a fresh one is created.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("aven.store")

_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        BEGIN;
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            language TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_messages_conversation ON messages(conversation_id, id);
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX idx_tasks_done ON tasks(done);
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'fired', 'cancelled')),
            created_at TEXT NOT NULL
        );
        CREATE INDEX idx_reminders_due ON reminders(status, due_at);
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        PRAGMA user_version = 1;
        COMMIT;
        """,
    ),
]
SCHEMA_VERSION = _MIGRATIONS[-1][0]
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _utc_iso(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    created_at: str


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    done: bool
    created_at: str
    completed_at: str | None


@dataclass(frozen=True)
class Reminder:
    id: int
    title: str
    due_at: str  # UTC ISO-8601
    status: str
    created_at: str


@dataclass(frozen=True)
class Message:
    id: int
    conversation_id: str
    role: str
    content: str
    language: str | None
    created_at: str


class StoreError(RuntimeError):
    """A storage operation failed."""


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        self._conn = self._open()
        try:
            self._migrate()
        except Exception:
            self._conn.close()
            raise

    # -- setup -----------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA user_version").fetchone()  # raises if not a database
            return conn
        except Exception:
            conn.close()
            raise

    def _open(self) -> sqlite3.Connection:
        if self._path != ":memory:":
            Path(self._path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        try:
            return self._connect()
        except sqlite3.DatabaseError:
            if self._path == ":memory:":
                raise
            source = Path(self._path)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            quarantine = source.with_name(f"{source.name}.corrupt-{stamp}")
            source.rename(quarantine)
            log.error("Database was unreadable; moved aside to %s and starting fresh", quarantine.name)
            return self._connect()

    def _migrate(self) -> None:
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise StoreError(
                    f"Database schema {current} is newer than this app supports ({SCHEMA_VERSION})"
                )
            for version, script in _MIGRATIONS:
                if version > current:
                    self._conn.executescript(script)
                    log.info("Applied database migration %d", version)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def health(self) -> dict:
        with self._lock:
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        return {"ok": True, "schema_version": version}

    # -- conversations ----------------------------------------------------------

    @staticmethod
    def new_conversation_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def valid_conversation_id(value: str) -> bool:
        return bool(_CONVERSATION_ID.match(value))

    def ensure_conversation(self, conversation_id: str) -> None:
        if not self.valid_conversation_id(conversation_id):
            raise ValueError("invalid conversation id")
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, created_at) VALUES (?, ?)",
                (conversation_id, _utc_iso()),
            )

    def add_message(
        self, conversation_id: str, role: str, content: str, language: str | None = None
    ) -> None:
        self.ensure_conversation(conversation_id)
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, language, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, role, content, language, _utc_iso()),
            )

    def recent_messages(self, conversation_id: str, limit: int = 20) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, max(1, min(limit, 500))),
            ).fetchall()
        return [Message(**dict(r)) for r in reversed(rows)]

    def delete_all_history(self) -> int:
        """Delete every conversation. Returns how many were removed, and only
        after confirming that none remain."""
        with self._lock:
            before = self._conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            self._conn.execute("DELETE FROM conversations")
            remaining = self._conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            leftover = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if remaining or leftover:
            raise StoreError("History deletion did not complete")
        return before

    # -- notes ------------------------------------------------------------------

    def add_note(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("note text is empty")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO notes (text, created_at) VALUES (?, ?)", (text, _utc_iso())
            )
            row = self._conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Note(**dict(row))

    def list_notes(self, limit: int = 50) -> list[Note]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [Note(**dict(r)) for r in rows]

    def search_notes(self, query: str, limit: int = 50) -> list[Note]:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notes WHERE text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                (f"%{escaped}%", max(1, min(limit, 500))),
            ).fetchall()
        return [Note(**dict(r)) for r in rows]

    # -- tasks ------------------------------------------------------------------

    def add_task(self, title: str) -> Task:
        title = title.strip()
        if not title:
            raise ValueError("task title is empty")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO tasks (title, created_at) VALUES (?, ?)", (title, _utc_iso())
            )
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
        return self._task(row)

    @staticmethod
    def _task(row: sqlite3.Row) -> Task:
        data = dict(row)
        data["done"] = bool(data["done"])
        return Task(**data)

    def list_tasks(self, include_done: bool = False, limit: int = 100) -> list[Task]:
        query = "SELECT * FROM tasks"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY id ASC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, (max(1, min(limit, 500)),)).fetchall()
        return [self._task(r) for r in rows]

    def complete_task(self, task_id: int) -> Task | None:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET done = 1, completed_at = ? WHERE id = ? AND done = 0",
                (_utc_iso(), task_id),
            )
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        task = self._task(row)
        return task if cur.rowcount == 1 else None

    def get_task(self, task_id: int) -> Task | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task(row) if row else None

    # -- reminders --------------------------------------------------------------

    def add_reminder(self, title: str, due_at: datetime) -> Reminder:
        title = title.strip() or "Reminder"
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO reminders (title, due_at, created_at) VALUES (?, ?, ?)",
                (title, _utc_iso(due_at), _utc_iso()),
            )
            row = self._conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return Reminder(**dict(row))

    def list_reminders(self, status: str = "pending", limit: int = 100) -> list[Reminder]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC LIMIT ?",
                (status, max(1, min(limit, 500))),
            ).fetchall()
        return [Reminder(**dict(r)) for r in rows]

    def due_reminders(self, now: datetime) -> list[Reminder]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE status = 'pending' AND due_at <= ? ORDER BY due_at",
                (_utc_iso(now),),
            ).fetchall()
        return [Reminder(**dict(r)) for r in rows]

    def mark_reminder_fired(self, reminder_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE reminders SET status = 'fired' WHERE id = ? AND status = 'pending'",
                (reminder_id,),
            )
        return cur.rowcount == 1

    # -- settings ---------------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
