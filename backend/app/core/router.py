"""Offline intent router: plain text in, a typed ``Intent`` out.

It never executes anything. Execution (and validation of anything that touches
the device) happens later in the assistant service and automation layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core import calc

_WAKE = re.compile(r"^\s*(?:(?:hey|hi|ok|okay)[\s,]+)?aven\b[\s,.:;!-]*", re.IGNORECASE)

_STOP = re.compile(r"^(?:stop|cancel|never\s?mind|quiet|ruko|ruk|thamb)\W*$", re.IGNORECASE)
_STOP_DEV = {"थांबा", "थांब", "रुको", "रुक"}
YES = re.compile(
    r"^(?:yes|yeah|yep|yup|ok|okay|sure|confirm|go ahead|do it|haan|ha|ho|hoy)\W*$",
    re.IGNORECASE,
)
YES_DEV = {"होय", "हो", "हाँ", "हां", "हा"}
NO = re.compile(r"^(?:no|nope|nah|cancel|don'?t|nahi|nako|stop)\W*$", re.IGNORECASE)
NO_DEV = {"नाही", "नको", "नहीं", "नही"}

_GREETING = re.compile(
    r"^(?:hi+|hello+|hey+|yo|namaste|namaskar|good\s+(?:morning|afternoon|evening))\W*$",
    re.IGNORECASE,
)
_GREETING_DEV = {"नमस्ते", "नमस्कार", "हॅलो", "हैलो"}
_HOW_ARE_YOU = re.compile(
    r"\b(?:how are you|how r u|how'?s it going|kasa ahes|kasa aahes|kasa ahe|kase aahat|"
    r"kaise ho|kaisa hai|kaise hain|kya haal)\b",
    re.IGNORECASE,
)
_HOW_ARE_YOU_DEV = ("कसा आहेस", "कसे आहात", "कैसे हो", "कैसे हैं", "क्या हाल")
_HELP = re.compile(r"^(?:help|what can you do|kya kar sakte ho)\W*$", re.IGNORECASE)
_TIME = re.compile(
    r"\b(?:what(?:'s| is)? the time|what time is it|current time|time now|tell me the time|"
    r"kiti vajle|kitne baje|time kya hai)\b",
    re.IGNORECASE,
)
_TIME_DEV = ("किती वाजले", "कितने बजे", "वेळ काय", "टाइम क्या", "समय क्या")
_DATE = re.compile(
    r"\b(?:today'?s date|what(?:'s| is) (?:the )?date|what day is it|what is today|"
    r"aaj ki (?:tarikh|date)|aajchi (?:tarikh|date)|aaj kaun ?sa din)\b",
    re.IGNORECASE,
)
_DATE_DEV = ("आजची तारीख", "आज की तारीख", "आज कौन सा दिन", "आज कोणता दिवस")

_REMINDER_ADD = re.compile(
    r"^\s*(?:please\s+)?(?:remind me|set (?:a )?reminder|add (?:a )?reminder|"
    r"create (?:a )?reminder|yaad dila(?:o|na)?|mala aathavan kar)\b",
    re.IGNORECASE,
)
_REMINDER_LIST = re.compile(
    r"^(?:show|list|read|what are|tell me)\b.*\breminders?\b|^(?:my )?reminders?\s*$",
    re.IGNORECASE,
)
_NOTE_ADD = re.compile(
    r"^(?:take a note|add (?:a )?note|note down|save (?:a )?note|make a note|note)\b"
    r"[\s:,-]*(?:that\b\s*)?(.+)$",
    re.IGNORECASE,
)
_NOTE_LIST = re.compile(
    r"^(?:(?:show|list|read|what are|open)\s+)?(?:me\s+)?(?:my\s+)?(?:all\s+)?notes?\s*$",
    re.IGNORECASE,
)
_NOTE_SEARCH = re.compile(
    r"^(?:search|find)\s+(?:my\s+)?notes?\s+(?:for|about)?\s*(.+)$", re.IGNORECASE
)
_TASK_ADD = re.compile(
    r"^(?:add (?:a )?task|new task|add to (?:my )?(?:tasks?|to-?do)(?: list)?|add (?:a )?to-?do|"
    r"todo|to-do)\b[\s:,-]*(?:to\s+)?(.+)$",
    re.IGNORECASE,
)
_TASK_LIST = re.compile(
    r"^(?:(?:show|list|read|what are)\s+)?(?:me\s+)?(?:my\s+)?(?:all\s+)?"
    r"(?:tasks|to-?dos?|to-?do list)\s*$",
    re.IGNORECASE,
)
_TASK_DONE = re.compile(
    r"^(?:(?:complete|finish|done with|mark)\s+(?:task\s+)?#?(\d+)(?:\s+(?:as\s+)?(?:done|completed?))?"
    r"|task\s+#?(\d+)\s+(?:done|completed?))\W*$",
    re.IGNORECASE,
)
_OPEN = re.compile(r"^(?:open|launch|start)\s+(?:the\s+|my\s+)?(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Intent:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


def strip_wake(text: str) -> str:
    """Remove a leading "Hey Aven" so the command itself can be routed."""
    return _WAKE.sub("", text, count=1).strip()


def _bare(text: str) -> str:
    return re.sub(r"[\s!?.,।]+$", "", text).strip()


def is_yes(text: str) -> bool:
    return bool(YES.match(text.strip())) or _bare(text) in YES_DEV


def is_no(text: str) -> bool:
    return bool(NO.match(text.strip())) or _bare(text) in NO_DEV


def route(text: str) -> Intent:
    """Classify ``text``. Unknown input becomes ``Intent("unknown")``."""
    if not text or not text.strip():
        return Intent("empty")
    command = strip_wake(text)
    if not command:
        return Intent("greeting")
    bare = _bare(command)

    if _STOP.match(command) or bare in _STOP_DEV:
        return Intent("stop")
    if _GREETING.match(command) or bare in _GREETING_DEV:
        return Intent("greeting")
    if _HOW_ARE_YOU.search(command) or any(p in command for p in _HOW_ARE_YOU_DEV):
        return Intent("how_are_you")
    if _HELP.match(command):
        return Intent("help")
    if _TIME.search(command) or any(p in command for p in _TIME_DEV):
        return Intent("time")
    if _DATE.search(command) or any(p in command for p in _DATE_DEV):
        return Intent("date")

    if _REMINDER_LIST.search(command):
        return Intent("reminder_list")
    if _REMINDER_ADD.match(command):
        return Intent("reminder_add", {"text": command})

    match = _NOTE_SEARCH.match(command)
    if match:
        return Intent("note_search", {"query": match.group(1).strip()})
    if _NOTE_LIST.match(command):
        return Intent("note_list")
    match = _NOTE_ADD.match(command)
    if match:
        return Intent("note_add", {"text": match.group(1).strip()})

    match = _TASK_DONE.match(command)
    if match:
        return Intent("task_done", {"id": int(match.group(1) or match.group(2))})
    if _TASK_LIST.match(command):
        return Intent("task_list")
    match = _TASK_ADD.match(command)
    if match:
        return Intent("task_add", {"title": match.group(1).strip()})

    expression = calc.to_expression(command)
    if expression:
        return Intent("calc", {"expression": expression})

    match = _OPEN.match(command)
    if match:
        return Intent("open", {"target": match.group(1).strip()})

    return Intent("unknown")
