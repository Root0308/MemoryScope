[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"
$envFile = Join-Path $projectRoot ".env"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Backend environment is missing. Run .\scripts\setup.ps1 first."
}

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
if (Test-Path -LiteralPath $envFile) {
    $uvicornArgs += @("--env-file", $envFile)
}

Push-Location $backendPath
try {
    & $venvPython @uvicornArgs
} finally {
    Pop-Location
}
