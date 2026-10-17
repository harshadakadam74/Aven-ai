# Troubleshooting

**`AVEN_AI_API_KEY` error when starting the backend** — the key must be at least 16 characters. Run `python scripts\generate_key.py` and put the output in `.env`. Restart through `run-backend.ps1` so `.env` is loaded.

**`ModuleNotFoundError: PySide6` / `fastapi`** — activate the virtual environment (`.\.venv\Scripts\Activate.ps1`) and run the `pip install` lines from [setup-windows.md](setup-windows.md).

**Scripts are blocked in PowerShell** — `Set-ExecutionPolicy -Scope Process Bypass` for the current window.

**"X isn't one of my approved apps"** — add it: `AVEN_AI_EXTRA_APPS=name=C:\full\path\app.exe`. Aven will not launch anything else.

**"No folders are approved yet" / "couldn't find a project called…"** — set `AVEN_AI_APPROVED_DIRS` to the parent folder (e.g. `C:\Users\you\Projects`). Only folders directly inside it can be opened.

**Android: "Can't reach the Aven server"** — emulator must use `http://10.0.2.2:8000`; a phone should use `adb reverse tcp:8000 tcp:8000` and `http://127.0.0.1:8000`. Confirm the backend answers at `http://127.0.0.1:8000/health` on the PC. Check `usesCleartextTraffic` and the INTERNET permission (see [setup-android.md](setup-android.md)).

**Android: "The server rejected the API key"** — re-enter it in Settings exactly as in `.env`.

**Database was unreadable** — Aven moved the bad file next to the original as `*.corrupt-<timestamp>` and started a new one. Your old data is still in that file.

**A reminder never popped up** — reminders are checked every 15 seconds while the desktop app is open. They are saved in Aven only; closed app means no alert until it is opened again (it will then fire anything overdue).

**Wrong reply language** — Stage 1 detection is a simple word-list heuristic; try a longer sentence. Better detection comes with the online AI stage.
