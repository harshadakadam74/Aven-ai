"""FastAPI application exposing the assistant to other devices (e.g. Android).

STATUS: written but NOT executed in the environment this stage was built in
(the package index was unreachable, so FastAPI could not be installed). The
logic it wraps (AssistantService, Store, schemas) is covered by the unit tests;
this wiring needs `pip install -r requirements.txt` and a run on your machine.
See docs/setup-windows.md.

Security defaults: every /api/v1 route needs the X-Aven-Key header, the server
binds to 127.0.0.1 unless you change AVEN_AI_HOST, chat is rate limited, request
bodies are validated with strict schemas, and device actions (opening apps) are
disabled for API callers.
"""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from app import __version__
from app.automation.actions import Executor
from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.database.store import Store, StoreError
from app.schemas.api import (
    ChatRequest,
    ChatResponse,
    DeleteHistoryOut,
    HealthOut,
    MessageOut,
    NoteCreate,
    NoteOut,
    ReminderOut,
    TaskCreate,
    TaskOut,
)
from app.services.assistant import AssistantService

log = logging.getLogger("aven.api")
MIN_API_KEY_LENGTH = 16


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
    executor: Executor | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if len(settings.api_key) < MIN_API_KEY_LENGTH:
        raise RuntimeError(
            f"Set AVEN_AI_API_KEY to a random value of at least {MIN_API_KEY_LENGTH} characters "
            "(run: python scripts/generate_key.py)."
        )
    if not settings.is_loopback:
        log.warning("Server is bound to a non-loopback address; use HTTPS and a firewall.")

    owns_store = store is None
    store = store or Store(settings.database_path)
    assistant = AssistantService(store, settings, executor, allow_actions=False)
    chat_limiter = RateLimiter(settings.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_store:
            store.close()

    app = FastAPI(
        title="Aven AI",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.env == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.env == "development" else None,
    )

    def require_key(x_aven_key: str | None = Header(default=None)) -> None:
        supplied = (x_aven_key or "").encode("utf-8")
        if not hmac.compare_digest(supplied, settings.api_key.encode("utf-8")):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    def limit_chat(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not chat_limiter.allow(client):
            raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        info = store.health()
        return HealthOut(status="ok", version=__version__, schema_version=info["schema_version"])

    @app.post(
        "/api/v1/chat",
        response_model=ChatResponse,
        dependencies=[Depends(require_key), Depends(limit_chat)],
    )
    def chat(body: ChatRequest) -> ChatResponse:
        reply = assistant.handle_text(body.message, body.conversation_id, body.private)
        return ChatResponse(**reply.to_dict())

    @app.get(
        "/api/v1/conversations/{conversation_id}/messages",
        response_model=list[MessageOut],
        dependencies=[Depends(require_key)],
    )
    def messages(conversation_id: str, limit: int = 50) -> list[MessageOut]:
        if not store.valid_conversation_id(conversation_id):
            raise HTTPException(status_code=422, detail="Invalid conversation id.")
        return [
            MessageOut(
                id=m.id, role=m.role, content=m.content, language=m.language, created_at=m.created_at
            )
            for m in store.recent_messages(conversation_id, limit)
        ]

    @app.delete(
        "/api/v1/conversations", response_model=DeleteHistoryOut, dependencies=[Depends(require_key)]
    )
    def delete_history() -> DeleteHistoryOut:
        try:
            return DeleteHistoryOut(deleted_conversations=store.delete_all_history())
        except StoreError as exc:
            log.error("History deletion failed")
            raise HTTPException(status_code=500, detail="History could not be deleted.") from exc

    @app.get("/api/v1/notes", response_model=list[NoteOut], dependencies=[Depends(require_key)])
    def list_notes(limit: int = 50) -> list[NoteOut]:
        return [NoteOut(id=n.id, text=n.text, created_at=n.created_at) for n in store.list_notes(limit)]

    @app.post(
        "/api/v1/notes", response_model=NoteOut, status_code=201, dependencies=[Depends(require_key)]
    )
    def create_note(body: NoteCreate) -> NoteOut:
        note = store.add_note(body.text)
        return NoteOut(id=note.id, text=note.text, created_at=note.created_at)

    @app.get("/api/v1/tasks", response_model=list[TaskOut], dependencies=[Depends(require_key)])
    def list_tasks(include_done: bool = False) -> list[TaskOut]:
        return [TaskOut(**t.__dict__) for t in store.list_tasks(include_done)]

    @app.post(
        "/api/v1/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_key)]
    )
    def create_task(body: TaskCreate) -> TaskOut:
        return TaskOut(**store.add_task(body.title).__dict__)

    @app.post(
        "/api/v1/tasks/{task_id}/complete",
        response_model=TaskOut,
        dependencies=[Depends(require_key)],
    )
    def complete_task(task_id: int) -> TaskOut:
        task = store.complete_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found or already completed.")
        return TaskOut(**task.__dict__)

    @app.get(
        "/api/v1/reminders", response_model=list[ReminderOut], dependencies=[Depends(require_key)]
    )
    def list_reminders(status: str = "pending") -> list[ReminderOut]:
        if status not in ("pending", "fired", "cancelled"):
            raise HTTPException(status_code=422, detail="status must be pending, fired or cancelled.")
        return [ReminderOut(**r.__dict__) for r in store.list_reminders(status)]

    return app
