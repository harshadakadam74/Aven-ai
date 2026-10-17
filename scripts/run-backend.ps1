# Start the Aven API server (needs backend dependencies installed in .venv).
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "load-env.ps1")
Set-Location (Join-Path $root "backend")
& (Join-Path $root ".venv\Scripts\python.exe") -m app.api.server
