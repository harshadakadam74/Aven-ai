"""Parse reminder wording such as "remind me to study at seven" or
"call mom in 10 minutes".

A bare hour like "at seven" is genuinely ambiguous (7 AM or 7 PM), so the parser
reports ``meridiem=None`` and lets the caller ask instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "an": 1,
}
_NUM = r"(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|an?)"
_HOUR = r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"

_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:remind me|set (?:a )?reminder|add (?:a )?reminder|"
    r"create (?:a )?reminder|yaad dila(?:o|na)?|mala aathavan kar)\b[\s,:-]*"
    r"(?:to\b|about\b|for\b|that\b)?\s*",
    re.IGNORECASE,
)
_RELATIVE = re.compile(
    rf"\bin\s+({_NUM})\s*(minutes?|mins?|hours?|hrs?|days?)\b", re.IGNORECASE
)
_ABSOLUTE = re.compile(
    rf"\b(?:at|@)\s*({_HOUR})(?:[:.](\d{{2}}))?(?!\d)"
    r"(?:\s*(a\.?m\.?|p\.?m\.?)(?![a-z]))?(?:\s*o'?clock)?",
    re.IGNORECASE,
)
_NOON = re.compile(r"\bat\s+noon\b", re.IGNORECASE)
_DAY = re.compile(r"\b(tomorrow|today|tonight)\b", re.IGNORECASE)
_HINT = re.compile(r"\b(?:in the\s+|this\s+)?(morning|afternoon|evening|night)\b", re.IGNORECASE)

_AM_WORDS = {"am", "a.m", "a.m.", "morning", "subah", "sakal", "sakali", "सकाळ", "सुबह"}
_PM_WORDS = {
    "pm", "p.m", "p.m.", "afternoon", "evening", "night", "tonight", "shaam", "raat",
    "dupar", "dopahar", "sandhyakal", "sandhyakali", "संध्याकाळ", "शाम", "रात", "दुपार", "दोपहर",
}


@dataclass(frozen=True)
class ReminderParse:
    title: str
    kind: str  # "none" | "relative" | "absolute" | "invalid"
    due: datetime | None = None  # set for "relative"
    hour: int | None = None  # as spoken, 0-23 or 1-12
    minute: int = 0
    meridiem: str | None = None  # "am" | "pm" | "24h" | None (ambiguous)
    day_offset: int | None = None  # explicit day word, else None

    @property
    def needs_meridiem(self) -> bool:
        return self.kind == "absolute" and self.meridiem is None


def _number(token: str) -> int:
    token = token.lower()
    return int(token) if token.isdigit() else _WORDS[token]


def strip_reminder_prefix(text: str) -> str:
    return _PREFIX.sub("", text, count=1)


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" \t,.;:-")
    text = re.sub(r"^(?:to|that|about|for|on|at)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:on|at|to|for)$", "", text, flags=re.IGNORECASE)
    return text.strip(" \t,.;:-")


def _remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return text


def parse_when(text: str, now: datetime) -> ReminderParse:
    """Find a time phrase in ``text`` and return it with the leftover title."""
    spans: list[tuple[int, int]] = []

    rel = _RELATIVE.search(text)
    if rel:
        amount = _number(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            delta = timedelta(minutes=amount)
        elif unit.startswith(("hour", "hr")):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)
        spans.append(rel.span())
        return ReminderParse(
            title=_clean_title(_remove_spans(text, spans)), kind="relative", due=now + delta
        )

    day_offset: int | None = None
    hint: str | None = None
    day = _DAY.search(text)
    if day:
        word = day.group(1).lower()
        day_offset = 1 if word == "tomorrow" else 0
        if word == "tonight":
            hint = "pm"
        spans.append(day.span())
    hint_match = _HINT.search(text)
    if hint_match:
        hint = "am" if hint_match.group(1).lower() == "morning" else "pm"
        spans.append(hint_match.span())

    noon = _NOON.search(text)
    if noon:
        spans.append(noon.span())
        return ReminderParse(
            title=_clean_title(_remove_spans(text, spans)), kind="absolute",
            hour=12, minute=0, meridiem="pm", day_offset=day_offset,
        )

    absolute = _ABSOLUTE.search(text)
    if not absolute:
        return ReminderParse(title=_clean_title(text), kind="none")

    spans.append(absolute.span())
    title = _clean_title(_remove_spans(text, spans))
    hour = _number(absolute.group(1))
    minute = int(absolute.group(2)) if absolute.group(2) else 0
    marker = absolute.group(3)
    if minute > 59:
        return ReminderParse(title=title, kind="invalid")

    if marker:
        if not 1 <= hour <= 12:
            return ReminderParse(title=title, kind="invalid")
        meridiem: str | None = "am" if marker.lower().startswith("a") else "pm"
    elif hour == 0 or 13 <= hour <= 23:
        meridiem = "24h"
    elif hour > 23:
        return ReminderParse(title=title, kind="invalid")
    elif hint:
        meridiem = hint
    else:
        meridiem = None
    return ReminderParse(
        title=title, kind="absolute", hour=hour, minute=minute,
        meridiem=meridiem, day_offset=day_offset,
    )


def parse_reminder_request(text: str, now: datetime) -> ReminderParse:
    return parse_when(strip_reminder_prefix(text), now)


def build_due(parse: ReminderParse, now: datetime, meridiem: str | None = None) -> datetime:
    """Turn an absolute parse into a concrete datetime (in ``now``'s timezone)."""
    if parse.kind == "relative" and parse.due is not None:
        return parse.due
    if parse.kind != "absolute" or parse.hour is None:
        raise ValueError("not an absolute time")
    chosen = meridiem or parse.meridiem
    if chosen == "24h":
        hour = parse.hour
    elif chosen == "am":
        hour = 0 if parse.hour == 12 else parse.hour
    elif chosen == "pm":
        hour = parse.hour if parse.hour == 12 else parse.hour + 12
    else:
        raise ValueError("AM or PM must be chosen first")
    candidate = now.replace(hour=hour, minute=parse.minute, second=0, microsecond=0)
    candidate += timedelta(days=parse.day_offset or 0)
    if parse.day_offset is None and candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def parse_meridiem(text: str) -> str | None:
    """Understand a reply like "pm", "7 pm", "evening" or "सकाळ"."""
    for token in re.findall(r"[a-z.]+|[ऀ-ॿ]+", text.lower()):
        if token in _AM_WORDS:
            return "am"
        if token in _PM_WORDS:
            return "pm"
    return None
