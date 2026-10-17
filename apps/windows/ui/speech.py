"""Non-blocking Windows speech output using an installed male SAPI voice."""

from __future__ import annotations

import pyttsx3
from PySide6.QtCore import QTimer


class SpeechOutput:
    def __init__(
        self,
        voice_id: str | None = None,
        rate: int | None = None,
        volume: float | None = None,
    ) -> None:
        self._engine = pyttsx3.init()
        installed_voices = self._engine.getProperty("voices")
        self.voices = [
            (
                voice.id,
                voice.name,
                str(getattr(voice, "gender", "unknown")).title(),
            )
            for voice in installed_voices
        ]
        male_voices = [
            voice
            for voice in installed_voices
            if "male" in str(getattr(voice, "gender", "")).lower()
        ]
        david_voice = next(
            (
                voice
                for voice in installed_voices
                if "david" in f"{voice.name} {voice.id}".lower()
            ),
            None,
        )
        selected_voice = next(
            (voice for voice in installed_voices if voice.id == voice_id),
            None,
        )
        selected_voice = selected_voice or (male_voices[0] if male_voices else david_voice)
        if selected_voice is None:
            raise RuntimeError("No usable Windows speech voice was found.")

        self.set_voice(selected_voice.id)
        self.rate = int(rate if rate is not None else self._engine.getProperty("rate"))
        self.volume = float(volume if volume is not None else self._engine.getProperty("volume"))
        self._engine.setProperty("rate", self.rate)
        self._engine.setProperty("volume", self.volume)
        self._engine.startLoop(False)
        self._timer = QTimer()
        self._timer.timeout.connect(self._engine.iterate)
        self._timer.start(10)

    def set_voice(self, voice_id: str) -> None:
        voice = next((item for item in self.voices if item[0] == voice_id), None)
        if voice is None:
            raise ValueError("That speech voice is no longer installed.")
        self._engine.setProperty("voice", voice[0])
        self.voice_id, self.voice_name, self.voice_gender = voice

    def set_rate(self, rate: int) -> None:
        self.rate = int(rate)
        self._engine.setProperty("rate", self.rate)

    def set_volume(self, volume: float) -> None:
        self.volume = min(1.0, max(0.0, float(volume)))
        self._engine.setProperty("volume", self.volume)

    def speak(self, text: str) -> None:
        self._engine.say(text)

    def stop(self) -> None:
        self._engine.stop()

    def close(self) -> None:
        self._timer.stop()
        self._engine.stop()
        self._engine.endLoop()