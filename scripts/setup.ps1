[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$frontendPath = Join-Path $projectRoot "frontend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "Python 3.11 or newer is required and was not found on PATH."
    }
    & $python.Source -m venv (Join-Path $backendPath ".venv")
}

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if ($null -eq $pnpm) {
    throw "pnpm 11.19.0 is required. Install it with: npm install --global pnpm@11.19.0"
}

Push-Location $backendPath
try {
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e ".[dev]"
} finally {
    Pop-Location
}

Push-Location $frontendPath
try {
    & $pnpm.Source install --frozen-lockfile
} finally {
    Pop-Location
}

Write-Host "MemoryScope dependencies are installed."
