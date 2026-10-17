# Architecture (Stage 1)

## Layers

```
 Windows app (PySide6) ──in-process──┐
                                     ▼
 Android app (Flutter) ──HTTP──▶ FastAPI ──▶ AssistantService ──▶ Store (SQLite)
                                                 │
                                                 ├─ router        text → typed Intent (never executes)
                                                 ├─ timeparse     reminder wording, AM/PM clarification
                                                 ├─ calc          safe arithmetic (ast, no eval)
                                                 └─ automation    AutomationPolicy → ActionProposal → Executor
```

- **Router** (`core/router.py`) classifies text into an `Intent`. It has no side effects.
- **AssistantService** (`services/assistant.py`) carries out intents, holds short-lived pending state (AM/PM question, "yes/no" confirmation, 5-minute expiry) and saves history.
- **AutomationPolicy** (`automation/actions.py`) turns "open X" into a validated `ActionProposal` or refuses with a user-safe message. The **Executor** only receives validated proposals and launches fixed argument lists with `shell=False`.
- **Store** (`database/store.py`) uses parameterized SQL, numbered migrations (`PRAGMA user_version`), and moves an unreadable database aside instead of deleting it.

## Decisions and deviations from the master prompt

| Prompt said | Stage 1 does | Why |
|---|---|---|
| SQLAlchemy | Standard-library `sqlite3` behind a `Store` class | Could not install packages while building, and I wanted the storage logic genuinely tested. The `Store` interface can be re-implemented on SQLAlchemy later without touching callers. |
| Pinned, tested dependency versions | Version ranges | The package index was unreachable, so the combination was not install-tested. Freeze a lock file after your first good run. |
| `apps/windows/platform/` folder | Omitted | A package named `platform` shadows Python's standard-library module of the same name when the app runs from that folder. Windows-specific adapters will use another name (e.g. `adapters/`). |
| Windows app talks to a backend | Runs the assistant in-process | Keeps the desktop app working with no server and no network. |
| Android works offline | Android needs the backend (Stage 1) | Windows Python code cannot run on Android. A Dart offline engine is not built yet, and the app says so when the server is unreachable. |
| Voice, wake word, memory, online AI | Not built | Stages 2 to 5. Disabled controls say which stage adds them. |

## Safety rules enforced (and tested)

- Only allowlisted apps, approved folders and `http(s)` URLs can be opened; `cmd`, `powershell`, `..`, absolute paths, symlinks that leave an approved folder, `javascript:`/`file:` URLs and URLs with embedded credentials are refused.
- A launch is reported as "I started X" only if the operating system accepted it; failures are reported as failures. It cannot prove a window is visible, so replies avoid claiming that.
- Reminders are stored in Aven only and the reply says so; nothing is added to an external calendar.
- API callers cannot trigger device actions (`allow_actions=False`), so a leaked key cannot open programs on your PC.
- History deletion is verified (rows counted afterwards) before success is reported.
- The API key is never logged or printed (`Settings.__repr__` hides it); the Android app stores it in secure storage.

## Known limits

- Language detection is a marker-word heuristic; short or mixed messages can be misclassified.
- Hindi and Marathi reply strings were written without native-speaker review. Please check them.
- Pending questions live in memory; restarting the app forgets them.
- Time handling assumes the computer's current time zone and does not special-case daylight-saving changes.
- The rate limiter is per process and keyed by client IP.
