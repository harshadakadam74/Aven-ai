# Dot-source this to load .env into the current PowerShell session:  . .\scripts\load-env.ps1
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
if (-not (Test-Path $envFile)) { Write-Host "No .env file found (copy .env.example to .env first)."; return }
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"'), "Process")
    }
}
Write-Host "Loaded .env into this session."
