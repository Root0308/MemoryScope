[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendPath = Join-Path $projectRoot "frontend"
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue

if ($null -eq $pnpm) {
    throw "pnpm 11.19.0 is required. Install it with: npm install --global pnpm@11.19.0"
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    throw "Frontend dependencies are missing. Run .\scripts\setup.ps1 first."
}

Push-Location $frontendPath
try {
    & $pnpm.Source run dev -- --host 127.0.0.1
} finally {
    Pop-Location
}
