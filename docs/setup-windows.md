# Windows setup

Supported: Windows 10/11, Python 3.12 (3.11 to 3.13 should work; only 3.13 was exercised, on Linux).

## 1. Environment

```powershell
cd aven-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
pip install -r apps\windows\requirements.txt
Copy-Item .env.example .env
python scripts\generate_key.py
```

Open `.env` in a text editor and paste the generated key after `AVEN_AI_API_KEY=`. This key is for the backend API. Online AI is optional: set `AI_PROVIDER=openai` and `AI_API_KEY` to enable it; leave them blank to use the local fallback. Keep `.env` private and out of source control. If PowerShell refuses to run scripts: `Set-ExecutionPolicy -Scope Process Bypass`.

Optional, in `.env`:

```
AVEN_AI_APPROVED_DIRS=C:\Users\you\Projects
AVEN_AI_EXTRA_APPS=chrome=C:\Program Files\Google\Chrome\Application\chrome.exe
```

Built in: Notepad, Calculator, Paint, File Explorer and VS Code (if `code` is on your PATH). Then "open my Scriptora project" opens `C:\Users\you\Projects\Scriptora`.

The desktop action registry can also be edited at `apps/windows/config/windows_actions.json`:

```json
{
	"applications": {
		"chrome": "C:/Program Files/Google/Chrome/Application/chrome.exe"
	},
	"approved_directories": ["C:/Users/you/Projects"]
}
```

## 2. Run the tests

```powershell
.\scripts\test.ps1
```

Run `python scripts/run_tests.py` to see the current backend and Windows test results. Some platform-specific tests may be skipped when Windows lacks the needed symlink or executable behavior.

## 3. Start the desktop app

```powershell
.\scripts\run-windows.ps1
```

The first desktop launch downloads the Whisper tiny multilingual model if needed, then warms it in the background; text chat stays available while **Mic** shows **Loading voice…**. After it is ready, speech recognition runs locally with automatic English, Hindi, Marathi and Hinglish-compatible detection. Click **Mic** to start recording; silence ends capture automatically, or click **Stop listening**. Voice diagnostics report capture, transcription, processing and speaking durations. Replies use installed Windows voices, selectable in **Voice settings**. The **Diagnostics** dialog shows microphone access, speech engine readiness, provider configuration and the supported Windows action registry. Audio is not sent to the online AI provider.

To run the app directly without activating the virtual environment, execute `python apps/windows/main.py` from the repository root after activating the environment.

If Windows blocks microphone access, enable microphone access for desktop apps in **Settings > Privacy & security > Microphone**. The app uses the default Windows recording device.

## 4. Start the API (needed only for Android)

```powershell
.\scripts\run-backend.ps1
```

Check it: `Invoke-RestMethod http://127.0.0.1:8000/health`. Interactive docs (development only): http://127.0.0.1:8000/docs.

## 5. Package an executable (later)

Not done in Stage 1. When it is, API keys stay out of the bundle; they come from `.env` or the environment.

## Backup and restore

Your data is the single SQLite file named by `DATABASE_URL`. Close Aven, copy the file to back up, copy it back to restore.

**The desktop app and the API do not share data by default.** The default `sqlite:///./aven_ai.db` is relative, so the desktop app creates `apps\windows\aven_ai.db` and the API creates `backend\aven_ai.db`. To use one shared database, set an absolute path in `.env`, for example `DATABASE_URL=sqlite:///C:/Users/you/aven/aven_ai.db`. Pending questions (like "AM or PM?") are never shared; they live in each running process.
