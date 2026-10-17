"""Aven AI for Windows (Stage 1). Run from this folder:  python main.py

Runs the assistant in-process, so it works with no backend server and no
internet. STATUS: written but not executed in the environment this stage was
built in (PySide6 could not be installed there); see docs/setup-windows.md.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from controllers.assistant_controller import AssistantController
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Aven AI")
    try:
        controller = AssistantController()
    except Exception as exc:  # noqa: BLE001 - show config problems instead of a silent exit
        QMessageBox.critical(None, "Aven AI could not start", str(exc))
        return 1
    window = MainWindow(controller)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
