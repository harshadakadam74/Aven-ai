"""Request and response schemas for the HTTP API (validated by Pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(_Strict):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    private: bool = False


class ChatResponse(BaseModel):
    text: str
    intent: str
    conversation_id: str
    language: str
    needs_input: str | None = None
    stop_speaking: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class NoteCreate(_Strict):
    text: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: int
    text: str
    created_at: str


class TaskCreate(_Strict):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _no_control_characters(cls, value: str) -> str:
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("title must not contain control characters")
        return value


class TaskOut(BaseModel):
    id: int
    title: str
    done: bool
    created_at: str
    completed_at: str | None = None


class ReminderOut(BaseModel):
    id: int
    title: str
    due_at: str
    status: str
    created_at: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    language: str | None = None
    created_at: str


class HealthOut(BaseModel):
    status: str
    version: str
    schema_version: int


class DeleteHistoryOut(BaseModel):
    deleted_conversations: int
