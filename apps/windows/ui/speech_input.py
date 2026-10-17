"""Offline multilingual microphone transcription for Windows."""

from __future__ import annotations

import threading

_MODEL = None
_MODEL_LOCK = threading.Lock()
_SUPPORTED_LANGUAGES = {"en", "hi", "mr"}
_MIN_LANGUAGE_PROBABILITY = 0.35


def _validate_language(language: str, probability: float) -> str:
    if language not in _SUPPORTED_LANGUAGES or probability < _MIN_LANGUAGE_PROBABILITY:
        raise RuntimeError(
            "I couldn't confidently detect English, Hindi, or Marathi. "
            "Please try again and speak clearly."
        )
    return language


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                from faster_whisper import WhisperModel
                from huggingface_hub.utils import LocalEntryNotFoundError

                try:
                    _MODEL = WhisperModel(
                        "tiny",
                        device="cpu",
                        compute_type="int8",
                        local_files_only=True,
                    )
                except LocalEntryNotFoundError:
                    _MODEL = WhisperModel(
                        "tiny",
                        device="cpu",
                        compute_type="int8",
                    )
    return _MODEL


def warm_model() -> str:
    """Load the local model before the first microphone request."""
    _get_model()
    return "ready"


def listen_and_transcribe(
    stop_event: threading.Event,
    language: str = "auto",
) -> tuple[str, str]:
    import numpy as np
    import sounddevice as sd

    model = _get_model()

    audio_chunks = []
    speech_started = False
    quiet_chunks = 0
    waiting_chunks = 0
    with sd.InputStream(samplerate=16_000, channels=1, dtype="float32") as stream:
        while not stop_event.is_set() and len(audio_chunks) < 120:
            chunk, _ = stream.read(4_000)
            samples = chunk[:, 0]
            volume = float(np.sqrt(np.mean(samples**2)))
            if not speech_started:
                waiting_chunks += 1
                if volume < 0.008:
                    if waiting_chunks >= 40:
                        break
                    continue
                speech_started = True

            audio_chunks.append(samples)
            quiet_chunks = quiet_chunks + 1 if volume < 0.006 else 0
            if quiet_chunks >= 6:
                break

    if not audio_chunks:
        raise RuntimeError("No speech detected. Press Mic and try speaking again.")

    audio = np.concatenate(audio_chunks)
    segments, info = model.transcribe(
        audio,
        beam_size=1,
        vad_filter=True,
        language=None if language == "auto" else language,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise RuntimeError("I couldn't understand that. Please try speaking again.")
    language = _validate_language(info.language, info.language_probability)
    return text, language