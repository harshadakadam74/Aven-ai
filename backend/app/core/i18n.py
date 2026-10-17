"""Reply texts for the offline assistant.

Only a handful of replies are localized in Stage 1 (greetings, status, help,
fallback, stop). Everything else is English. The Hindi and Marathi strings are
written to be gender-neutral and should be reviewed by a native speaker.
Aven never claims feelings, so "how are you" is answered with readiness.
"""

from __future__ import annotations

_TEXT: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "en": [
            "Hey! I'm here. What can I do for you?",
            "Hi again! What would you like to do?",
            "Hello! How can I help?",
        ],
        "hi": [
            "नमस्ते! मैं यहाँ हूँ। मैं आपकी क्या मदद करूँ?",
            "फिर से नमस्ते! आज क्या करना है?",
        ],
        "mr": [
            "नमस्कार! मी इथे आहे. मी तुमची काय मदत करू?",
            "पुन्हा नमस्कार! आज काय करायचं आहे?",
        ],
    },
    "how_are_you": {
        "en": ["I'm ready and here to help! How are you doing?"],
        "hi": ["मैं तैयार हूँ और मदद के लिए यहाँ हूँ! आप कैसे हैं?"],
        "mr": ["मी तयार आहे आणि मदतीसाठी इथे आहे! तुम्ही कसे आहात?"],
    },
    "help": {
        "en": [
            "Offline I can tell the time and date, do calculations, keep notes, tasks and "
            "reminders, and open apps, folders and projects you've approved."
        ],
        "hi": [
            "ऑफ़लाइन मैं समय और तारीख़ बता सकता/सकती हूँ, गणना, नोट्स, टास्क और रिमाइंडर "
            "संभाल सकता/सकती हूँ, और स्वीकृत ऐप खोल सकता/सकती हूँ।"
        ],
        "mr": [
            "ऑफलाइन मी वेळ आणि तारीख सांगू शकतो/शकते, गणित, नोट्स, टास्क आणि रिमाइंडर सांभाळू "
            "शकतो/शकते, आणि मान्य केलेले अ‍ॅप्स उघडू शकतो/शकते."
        ],
    },
    "fallback": {
        "en": [
            "I can't answer that offline yet. I can help with the time, date, calculations, "
            "notes, tasks, reminders and opening approved apps."
        ],
        "hi": [
            "यह अभी ऑफ़लाइन संभव नहीं है। समय, तारीख़, गणना, नोट्स, टास्क, रिमाइंडर और स्वीकृत "
            "ऐप खोलने में मदद उपलब्ध है।"
        ],
        "mr": [
            "हे सध्या ऑफलाइन शक्य नाही. वेळ, तारीख, गणित, नोट्स, टास्क, रिमाइंडर आणि मान्य अ‍ॅप्स "
            "उघडण्यात मदत उपलब्ध आहे."
        ],
    },
    "stop": {
        "en": ["Okay, stopped."],
        "hi": ["ठीक है, रुक गया।"],
        "mr": ["ठीक आहे, थांबलो."],
    },
}


def text(key: str, lang: str, variant: int = 0) -> str:
    """Return the reply for ``key`` in ``lang`` (falls back to English)."""
    options = _TEXT[key].get(lang) or _TEXT[key]["en"]
    return options[variant % len(options)]
