$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$backendPort = 8100
$aiPort = 8101
$frontendPort = 5175

if (-not (Test-Path -LiteralPath $pythonPath)) {
  throw "Python virtual environment was not found: $pythonPath"
}

function Start-DevTerminal([string]$title, [string]$workingDirectory, [string]$command) {
  Start-Process powershell.exe -ArgumentList @(
    '-NoExit',
    '-Command',
    "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location -LiteralPath '$workingDirectory'; $command"
  )
}

# Bind every development server to the LAN interface for team testing.
Start-DevTerminal "TOUR Backend $backendPort" (Join-Path $projectRoot 'backend') "& '$pythonPath' -m uvicorn app.main:app --reload --host 0.0.0.0 --port $backendPort"
Start-DevTerminal "TOUR AI $aiPort" $projectRoot "& '$pythonPath' -m uvicorn ai_server.app.main:app --reload --host 0.0.0.0 --port $aiPort"
$frontendCommand = "`$env:VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:$backendPort'; `$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:$aiPort'; npm run dev -- --host 0.0.0.0 --port $frontendPort --strictPort"
Start-DevTerminal "TOUR Frontend $frontendPort" (Join-Path $projectRoot 'frontend') $frontendCommand

Write-Host "TP2-3 Backend $backendPort, AI Server $aiPort, and Frontend $frontendPort started in separate windows."
Write-Host "Local URL: http://localhost:$frontendPort"
Write-Host "Team LAN URL: http://192.168.0.22:$frontendPort"
