"""Main dashboard window for text chat, spoken replies, status and reminders.

Controls for features that do not exist yet (microphone input and voice
enrollment) are shown disabled with a tooltip saying which stage adds them.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from controllers.assistant_controller import AssistantController
from ui.orb import OrbWidget
from ui.speech import SpeechOutput
from ui.speech_input import listen_and_transcribe, warm_model

STYLE = """
QWidget { background: #0b1020; color: #e5e9f5; font-family: 'Segoe UI'; font-size: 14px; }
QLabel#title { font-size: 22px; font-weight: 600; }
QLabel#tagline, QLabel#status { color: #8b93b0; }
QTextBrowser, QLineEdit { background: #121a33; border: 1px solid #25305a; border-radius: 12px; padding: 8px; }
QPushButton { background: #22d3ee; color: #04121a; border: none; border-radius: 12px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: #67e8f9; }
QPushButton:disabled { background: #1b2447; color: #5b6488; }
QCheckBox { color: #8b93b0; }
"""


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 - surface any failure in the UI
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)


class MainWindow(QMainWindow):
    def __init__(self, controller: AssistantController) -> None:
        super().__init__()
        self._controller = controller
        self._pool = QThreadPool.globalInstance()
        self.setWindowTitle("Aven AI")
        self.resize(560, 760)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("Aven AI")
        title.setObjectName("title")
        tagline = QLabel("Your AI. Your Voice. Your World.")
        tagline.setObjectName("tagline")
        self._orb = OrbWidget()
        self._state_label = QLabel("Idle")
        self._state_label.setObjectName("status")
        self._state_label.setAlignment(Qt.AlignCenter)
        self._mode_label = QLabel(controller.mode_label)
        self._mode_label.setObjectName("status")
        self._input_language = controller.store.get_setting("voice.input_language", "auto")
        if self._input_language not in {"auto", "en", "hi", "mr"}:
            self._input_language = "auto"
        try:
            rate = self._setting_int("voice.rate", 175, 120, 240)
            volume = self._setting_int("voice.volume", 100, 0, 100) / 100
            self._speaker = SpeechOutput(
                voice_id=controller.store.get_setting("voice.output_id"),
                rate=rate,
                volume=volume,
            )
            self._voice_label = QLabel(self._voice_status())
        except Exception as exc:  # noqa: BLE001 - keep text chat available without speech
            self._speaker = None
            self._voice_label = QLabel(f"Spoken replies unavailable: {exc}")
        self._voice_label.setObjectName("status")
        self._listen_stop = None
        self._speech_ready = False

        self._transcript = QTextBrowser()
        self._transcript.setOpenExternalLinks(False)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message, e.g. “remind me to study at 7 pm”")
        self._input.returnPressed.connect(self._send)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._send)

        self._mic = QPushButton("Mic")
        self._mic.setText("Loading voice…")
        self._mic.setEnabled(False)
        self._mic.setToolTip("Start voice input in English, Hindi, or Marathi.")
        self._mic.clicked.connect(self._toggle_listening)
        self._stop_speaking = QPushButton("Stop speaking")
        self._stop_speaking.setEnabled(self._speaker is not None)
        self._stop_speaking.setToolTip("Stop Aven's spoken reply.")
        self._stop_speaking.clicked.connect(self._stop_voice)
        self._voice_settings = QPushButton("Voice settings")
        self._voice_settings.clicked.connect(self._open_voice_settings)

        self._private = QCheckBox("Private session (don't save this conversation)")
        clear = QPushButton("Clear history")
        clear.clicked.connect(self._clear_history)
        new_chat = QPushButton("New chat")
        new_chat.clicked.connect(self._new_chat)

        row = QHBoxLayout()
        row.addWidget(self._input, 1)
        row.addWidget(self._send_button)
        tools = QHBoxLayout()
        tools.addWidget(self._mic)
        tools.addWidget(self._stop_speaking)
        tools.addWidget(self._voice_settings)
        tools.addStretch(1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(new_chat)
        actions.addWidget(clear)

        for widget in (title, tagline, self._orb, self._state_label):
            layout.addWidget(widget)
        layout.addWidget(self._transcript, 1)
        layout.addLayout(row)
        layout.addLayout(tools)
        layout.addLayout(actions)
        layout.addWidget(self._private)
        layout.addWidget(self._mode_label)
        layout.addWidget(self._voice_label)
        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)

        self._append("Aven", "Hi! Type a message to get started. Say “help” to see what I can do offline.")

        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(15_000)

        self._voice_label.setText("Loading offline speech model…")
        worker = _Worker(warm_model)
        worker.signals.done.connect(self._on_speech_ready)
        worker.signals.failed.connect(self._on_speech_unavailable)
        self._pool.start(worker)

    # -- helpers ----------------------------------------------------------------

    def _set_state(self, state: str, label: str) -> None:
        self._orb.set_state(state)
        self._state_label.setText(label)

    def _setting_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self._controller.store.get_setting(key, str(default)))
        except (TypeError, ValueError):
            return default
        return min(maximum, max(minimum, value))

    def _voice_status(self) -> str:
        if self._speaker is None:
            return "Spoken replies unavailable"
        return f"Spoken replies: {self._speaker.voice_gender} ({self._speaker.voice_name})"

    @Slot(object)
    def _on_speech_ready(self, _result) -> None:
        self._speech_ready = True
        self._mic.setText("Mic")
        self._mic.setEnabled(True)
        self._voice_label.setText(f"Speech ready | {self._voice_status()}")

    @Slot(str)
    def _on_speech_unavailable(self, message: str) -> None:
        self._mic.setText("Mic unavailable")
        self._mic.setEnabled(False)
        self._voice_label.setText(f"Speech input unavailable: {message}")

    def _append(self, who: str, text: str) -> None:
        safe = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        )
        color = "#22d3ee" if who == "Aven" else "#a78bfa"
        self._transcript.append(f"<p><b style='color:{color}'>{who}</b><br>{safe}</p>")

    # -- actions ----------------------------------------------------------------

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._append("You", text)
        self._send_button.setEnabled(False)
        self._set_state("thinking", "Thinking…")
        private = self._private.isChecked()
        worker = _Worker(lambda: self._controller.send(text, private))
        worker.signals.done.connect(self._on_reply)
        worker.signals.failed.connect(self._on_error)
        self._pool.start(worker)

    def _toggle_listening(self) -> None:
        if not self._speech_ready:
            return
        if self._listen_stop is not None:
            self._listen_stop.set()
            self._mic.setText("Processing…")
            self._mic.setEnabled(False)
            return

        self._stop_voice()
        self._listen_stop = threading.Event()
        self._mic.setText("Stop listening")
        self._send_button.setEnabled(False)
        self._input.setEnabled(False)
        self._set_state("listening", "Listening…")
        worker = _Worker(lambda: listen_and_transcribe(self._listen_stop, self._input_language))
        worker.signals.done.connect(self._on_transcription)
        worker.signals.failed.connect(self._on_error)
        self._pool.start(worker)

    @Slot(object)
    def _on_transcription(self, result) -> None:
        text, language = result
        language_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
        self._listen_stop = None
        self._mic.setText("Mic")
        self._mic.setEnabled(True)
        self._voice_label.setText(
            f"Input: {language_names.get(language, language)} | {self._voice_status()}"
            if self._speaker is not None
            else f"Input: {language_names.get(language, language)}"
        )
        self._input.setEnabled(True)
        self._input.setText(text)
        self._send()

    @Slot(object)
    def _on_reply(self, reply) -> None:
        self._append("Aven", reply.text)
        if self._speaker is not None:
            try:
                self._speaker.speak(reply.text)
            except Exception as exc:  # noqa: BLE001 - speech must not interrupt text chat
                self._voice_label.setText(f"Spoken replies unavailable: {exc}")
                self._stop_speaking.setEnabled(False)
        self._send_button.setEnabled(True)
        self._set_state("idle", "Idle")
        self._input.setFocus()

    def _stop_voice(self) -> None:
        if self._speaker is not None:
            self._speaker.stop()

    def _open_voice_settings(self) -> None:
        original_voice = self._speaker.voice_id if self._speaker is not None else None
        original_rate = self._speaker.rate if self._speaker is not None else 175
        original_volume = round(self._speaker.volume * 100) if self._speaker is not None else 100
        dialog = QDialog(self)
        dialog.setWindowTitle("Voice settings")
        form = QFormLayout(dialog)

        voices = QComboBox()
        if self._speaker is not None:
            for voice_id, name, gender in self._speaker.voices:
                voices.addItem(f"{gender} - {name}", voice_id)
            voices.setCurrentIndex(max(0, voices.findData(self._speaker.voice_id)))
        else:
            voices.addItem("No installed speech voices")
            voices.setEnabled(False)
        form.addRow("Spoken voice", voices)

        languages = QComboBox()
        for label, code in (
            ("Automatic (English, Hindi, Marathi)", "auto"),
            ("English", "en"),
            ("Hindi", "hi"),
            ("Marathi", "mr"),
        ):
            languages.addItem(label, code)
        languages.setCurrentIndex(max(0, languages.findData(self._input_language)))
        form.addRow("Recognize speech as", languages)

        rate = QSlider(Qt.Horizontal)
        rate.setRange(120, 240)
        rate.setValue(self._speaker.rate if self._speaker is not None else 175)
        rate.setEnabled(self._speaker is not None)
        rate_label = QLabel(str(rate.value()))
        rate.valueChanged.connect(lambda value: rate_label.setText(str(value)))
        rate_row = QHBoxLayout()
        rate_row.addWidget(rate, 1)
        rate_row.addWidget(rate_label)
        form.addRow("Speech speed", rate_row)

        volume = QSlider(Qt.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(round(self._speaker.volume * 100) if self._speaker is not None else 100)
        volume.setEnabled(self._speaker is not None)
        volume_label = QLabel(f"{volume.value()}%")
        volume.valueChanged.connect(lambda value: volume_label.setText(f"{value}%"))
        volume_row = QHBoxLayout()
        volume_row.addWidget(volume, 1)
        volume_row.addWidget(volume_label)
        form.addRow("Volume", volume_row)

        test_voice = QPushButton("Test voice")
        test_voice.setEnabled(self._speaker is not None)
        if self._speaker is not None:
            test_voice.clicked.connect(
                lambda: self._preview_voice(
                    voices.currentData(), rate.value(), volume.value() / 100
                )
            )
        form.addRow(test_voice)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._input_language = languages.currentData()
            self._controller.store.set_setting("voice.input_language", self._input_language)
            if self._speaker is not None:
                self._apply_voice_settings(voices.currentData(), rate.value(), volume.value())
        elif self._speaker is not None and original_voice is not None:
            self._apply_voice_settings(
                original_voice,
                original_rate,
                original_volume,
                persist=False,
            )

    def _preview_voice(self, voice_id: str, rate: int, volume: float) -> None:
        if self._speaker is None:
            return
        self._apply_voice_settings(voice_id, rate, round(volume * 100), persist=False)
        self._speaker.speak("Hello, I am Aven. नमस्कार, मी आवेन आहे.")

    def _apply_voice_settings(
        self,
        voice_id: str,
        rate: int,
        volume: int,
        persist: bool = True,
    ) -> None:
        if self._speaker is None:
            return
        self._speaker.set_voice(voice_id)
        self._speaker.set_rate(rate)
        self._speaker.set_volume(volume / 100)
        self._voice_label.setText(self._voice_status())
        if persist:
            self._controller.store.set_setting("voice.output_id", voice_id)
            self._controller.store.set_setting("voice.rate", str(rate))
            self._controller.store.set_setting("voice.volume", str(volume))

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._append("Aven", f"Something went wrong: {message}")
        self._listen_stop = None
        self._mic.setText("Mic")
        self._mic.setEnabled(True)
        self._send_button.setEnabled(True)
        self._input.setEnabled(True)
        self._set_state("error", "Error — you can try again")

    def _check_reminders(self) -> None:
        try:
            for reminder in self._controller.poll_due_reminders():
                self._append("Aven", f"⏰ Reminder: {reminder.title}")
                QApplication.beep()
        except Exception as exc:  # noqa: BLE001 - never crash the UI from a timer
            self._set_state("error", f"Reminder check failed: {exc}")

    def _new_chat(self) -> None:
        self._controller.new_conversation()
        self._transcript.clear()
        self._append("Aven", "Started a new conversation.")

    def _clear_history(self) -> None:
        answer = QMessageBox.question(
            self, "Clear history", "Delete all saved conversations? Notes, tasks and reminders are kept."
        )
        if answer != QMessageBox.Yes:
            return
        try:
            count = self._controller.clear_history()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Clear history", f"History could not be deleted: {exc}")
            return
        self._transcript.clear()
        self._append("Aven", f"Deleted {count} saved conversation(s).")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._reminder_timer.stop()
        if self._listen_stop is not None:
            self._listen_stop.set()
        self._pool.waitForDone(2000)
        if self._speaker is not None:
            self._speaker.close()
        self._controller.close()
        super().closeEvent(event)
