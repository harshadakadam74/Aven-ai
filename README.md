# Aven AI

**Your AI. Your Voice. Your World.**

A personal assistant for Windows and Android ("Hey Aven"; Marathi, Hindi, English, Hinglish). The Windows desktop app supports local speech, safe Windows actions, and an optional configured online AI provider. Android and the backend API remain separate clients of the local command engine.

## Status (read this first)

| Piece | State |
|---|---|
| Offline command engine (time, date, calculator, notes, tasks, reminders, open allowlisted apps/folders/projects/URLs) | Built and tested |
| SQLite storage, migrations, corrupt-database recovery | **Built and tested** |
| Automation safety (allowlist, approved folders, path-traversal and symlink checks, URL checks, no shell) | **Built and tested** |
| Windows desktop controller (reminder polling, history, optional AI provider) | Built and tested |
| Windows desktop window (PySide6) | Local speech input/output, silence detection, interruption, voice settings and diagnostics |
| FastAPI backend (`/health`, `/api/v1/chat`, notes, tasks, reminders, history) | Written, **not run** (FastAPI could not be installed). Schemas are tested |
| Flutter Android app (chat, settings, secure key storage) | Written, **not built or run** (no Flutter SDK available). Dart tests are written but have **never been executed** |
| Windows speech | Offline push-to-talk transcription for English, Hindi, Marathi and Hinglish-compatible recognition; installed Windows voices are selectable. Android voice is not built. |
| "Hey Aven" wake word, voice enrollment, speaker verification | Not built (Stage 3) |
| Online AI conversation | Optional OpenAI-compatible provider configured with `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` and `AI_BASE_URL`; local commands continue to work without it |
| Long-term memory | Not built (Stage 5) |
| Messaging, email, calendar, Windows-to-Android pairing | Not built (Stage 7) |

The "not run" items were checked for syntax only. Expect a first-run fix or two when you launch them; the steps below are how to find out quickly.

## Quick start (Windows PowerShell)

Full details: [docs/setup-windows.md](docs/setup-windows.md) and [docs/setup-android.md](docs/setup-android.md).

```powershell
cd aven-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt -r apps\windows\requirements.txt
Copy-Item .env.example .env
python scripts\generate_key.py        # put the output in .env as AVEN_AI_API_KEY

.\scripts\test.ps1                    # run all Python tests (should report 73 + 4 passing)
.\scripts\run-windows.ps1             # desktop app
.\scripts\run-backend.ps1             # API for Android (http://127.0.0.1:8000/health)
```

Try in the desktop app: click **Mic** and speak; silence ends capture automatically, or click **Stop listening**. Aven transcribes locally and speaks its reply. **Voice settings** lets you select an installed voice, input language, speed and volume. **Diagnostics** shows microphone, speech, AI-provider and supported-action status. Unknown text uses online AI only when configured; otherwise Aven gives an offline fallback. You can also type: `what time is it`, `what is 12 times 5`, `take a note buy milk`, `add task call mom`, `remind me to study at seven` (Aven asks AM or PM), `open notepad`.

## Layout

```
backend/app/core         config, intent router, calculator, time parsing, language detection, rate limit
backend/app/database     SQLite store and migrations
backend/app/automation   typed, allowlisted device actions
backend/app/services     AssistantService (ties it together)
backend/app/api          FastAPI app (for Android)
backend/app/schemas      request/response validation
apps/windows             PySide6 desktop app (runs the assistant in-process)
apps/android             Flutter app (talks to the backend)
docs/                    architecture, setup, API reference, troubleshooting
scripts/                 key generator, test runner, PowerShell launchers
```

## Privacy and safety in Stage 1

- Speech audio is transcribed locally by Whisper and is not sent to the online AI provider. Unknown text is sent to the configured provider only when explicitly enabled with `AI_PROVIDER` and `AI_API_KEY`.
- Conversation history is saved locally; turn it off with `AVEN_AI_STORE_HISTORY=false`, use a private session in the app, or delete it with **Clear history**.
- Aven only opens explicitly supported or configured apps and folders under approved directories in `apps/windows/config/windows_actions.json` or `AVEN_AI_APPROVED_DIRS`. It never runs shell text.
- The API requires an API key, listens on localhost by default, and cannot launch programs on your PC.

See [docs/architecture.md](docs/architecture.md) for design decisions and how Stage 1 differs from the master prompt.
