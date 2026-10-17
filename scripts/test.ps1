# Run all Python tests.
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $PSScriptRoot "run_tests.py")
