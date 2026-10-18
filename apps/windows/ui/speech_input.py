"""Offline multilingual microphone transcription for Windows."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

_MODEL = None
_MODEL_LOCK = threading.Lock()
_SUPPORTED_LANGUAGES = {"en", "hi", "mr", "ur"}
_MIN_LANGUAGE_PROBABILITY = 0.35


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    listening_seconds: float
    transcription_seconds: float


class _EnergyVAD:
    def __init__(self) -> None:
        self.noise_level = 0.003
        self.speech_started = False
        self.quiet_chunks = 0

    def update(self, samples) -> tuple[float, bool]:
        import numpy as np

        volume = float(np.sqrt(np.mean(samples**2)))
        threshold = max(0.0045, self.noise_level * 2.8)
        active = volume >= threshold
        if active:
            self.speech_started = True
            self.quiet_chunks = 0
        elif self.speech_started:
            self.quiet_chunks += 1
        else:
            self.noise_level = self.noise_level * 0.9 + volume * 0.1
        return volume, active


def _validate_language(language: str, probability: float) -> str:
    if language not in _SUPPORTED_LANGUAGES or probability < _MIN_LANGUAGE_PROBABILITY:
        raise RuntimeError(
            "I couldn't confidently detect English, Hindi, Marathi, or Hinglish. "
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

    started_at = time.perf_counter()
    audio_chunks = []
    vad = _EnergyVAD()
    pre_roll = deque(maxlen=3)
    waiting_chunks = 0
    with sd.InputStream(samplerate=16_000, channels=1, dtype="float32") as stream:
        while not stop_event.is_set() and waiting_chunks < 300:
            chunk, _ = stream.read(1_600)
            samples = chunk[:, 0]
            _, active = vad.update(samples)
            waiting_chunks += 1
            if not vad.speech_started:
                pre_roll.append(samples)
                if waiting_chunks >= 150:
                    break
                continue
            if not audio_chunks:
                audio_chunks.extend(pre_roll)
            audio_chunks.append(samples)
            if vad.quiet_chunks >= 8:
                break

    listening_seconds = time.perf_counter() - started_at
    if not audio_chunks:
        raise RuntimeError("No speech detected. Press Mic and try speaking again.")

    audio = np.concatenate(audio_chunks)
    transcription_started = time.perf_counter()
    segments, info = model.transcribe(
        audio,
        beam_size=1,
        vad_filter=True,
        language=None if language == "auto" else language,
    )
    text = " ".join(segment.text.strip() for segment in segments).strip()
    transcription_seconds = time.perf_counter() - transcription_started
    if not text:
        raise RuntimeError("I couldn't understand that. Please try speaking again.")
    language = _validate_language(info.language, info.language_probability)
    return TranscriptionResult(text, language, listening_seconds, transcription_seconds)