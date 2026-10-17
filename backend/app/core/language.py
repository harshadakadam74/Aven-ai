"""Lightweight language detection for Marathi, Hindi, English and Hinglish.

This is a marker-word heuristic, not a trained model. It is good enough to pick
a reply language for the offline commands in Stage 1 and is deliberately small
and predictable. Stage 4 can replace it with an online provider.

Returned codes: ``en``, ``hi``, ``mr``, ``hinglish`` (romanized Hindi, usually
mixed with English).
"""

from __future__ import annotations

import re

_DEVANAGARI_TOKEN = re.compile(r"[ऀ-ॿ]+")
_LATIN_TOKEN = re.compile(r"[a-z']+")

_MARATHI_DEVANAGARI = {
    "आहे", "आहेस", "आहात", "आहेत", "मला", "काय", "कसा", "कसे", "कसं", "तुला",
    "करायचा", "करायचं", "करायची", "तुम्ही", "माझा", "माझी", "नको", "होय", "सांग",
}
_HINDI_DEVANAGARI = {
    "है", "हैं", "हूँ", "हूं", "मुझे", "क्या", "कैसे", "को", "का", "की", "के",
    "नहीं", "आप", "मैं", "मेरा", "मेरी", "बताओ", "करो", "हाँ", "हां",
}
_MARATHI_LATIN = {
    "ahe", "ahes", "aahe", "aahes", "aahat", "kasa", "kase", "kay", "mala", "tula",
    "karaycha", "karaychi", "karaycha", "majha", "mazi", "nako", "hoy", "sang",
    "kiti", "vajle", "aathavan", "tumhi",
}
_HINDI_LATIN = {
    "hai", "hain", "hoon", "hun", "mujhe", "kya", "kaise", "kaisa", "bhejo", "karo",
    "ko", "main", "mera", "meri", "haan", "yaad", "dilao", "baje", "kitne", "aap",
    "tum", "bata", "batao", "kaun", "kab", "kyun",
}

REPLY_LANGUAGE = {"en": "en", "hi": "hi", "mr": "mr", "hinglish": "en"}


def detect_language(text: str, default: str = "en") -> str:
    """Guess the language of ``text``; ``default`` breaks ties."""
    devanagari = _DEVANAGARI_TOKEN.findall(text)
    if devanagari:
        mr = sum(1 for tok in devanagari if tok in _MARATHI_DEVANAGARI)
        hi = sum(1 for tok in devanagari if tok in _HINDI_DEVANAGARI)
        if mr > hi:
            return "mr"
        if hi > mr:
            return "hi"
        return default if default in ("hi", "mr") else "hi"

    tokens = _LATIN_TOKEN.findall(text.lower())
    mr = sum(1 for tok in tokens if tok in _MARATHI_LATIN)
    hi = sum(1 for tok in tokens if tok in _HINDI_LATIN)
    if mr > hi:
        return "mr"
    if hi > 0:
        return "hinglish"
    return "en"
