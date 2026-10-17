# Start the Aven desktop app (needs PySide6 installed in .venv).
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "load-env.ps1")
Set-Location (Join-Path $root "apps\windows")
& (Join-Path $root ".venv\Scripts\python.exe") main.py
