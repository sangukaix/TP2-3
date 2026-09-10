$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$backendPort = 8100
$aiPort = 8112
$frontendPort = 5176
$projectTreePort = 8501

# Load .env into this PowerShell process so child server windows use the same settings.
function Import-ProjectEnv([string]$envPath) {
  if (-not (Test-Path -LiteralPath $envPath)) { return }
  foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
    if ($line -match '^\s*([^#=\s]+)\s*=\s*(.*?)\s*$') {
      $key = $matches[1]
      $value = $matches[2]
      if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
  }
}

Import-ProjectEnv (Join-Path $projectRoot '.env')

if (-not (Test-Path -LiteralPath $pythonPath)) {
  throw "Python virtual environment was not found: $pythonPath"
}

# AI Server를 띄우기 전에 개인 GPU 노트북의 Ollama 연결을 짧게 확인한다.
# 연결 실패여도 지도·화면 서버는 계속 실행하되, local_first 기획 생성이 실패할 이유를
# 시작 시점에 바로 알린다. 주소·API 키 등 민감한 값은 출력하지 않는다.
function Test-RemoteOllamaConnection {
  $baseUrl = ([string]$env:LOCAL_LLM_BASE_URL).Trim().TrimEnd('/')
  if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    Write-Warning 'Remote Ollama check skipped: LOCAL_LLM_BASE_URL is missing.'
    return
  }
  try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/tags" -TimeoutSec 5
    $models = @($response.models | ForEach-Object { [string]$_.name })
    $qwenOk = $models -contains ([string]$env:OLLAMA_QWEN_MODEL)
    $gemmaOk = $models -contains ([string]$env:OLLAMA_GEMMA_MODEL)
    if ($qwenOk -and $gemmaOk) {
      Write-Host 'Remote Ollama check passed: Qwen and Gemma are reachable.'
    } else {
      Write-Warning 'Remote Ollama is reachable, but a configured Qwen or Gemma model is missing.'
    }
  } catch {
    $localAddresses = @(
      Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
        ForEach-Object { "$($_.InterfaceAlias)=$($_.IPAddress)" }
    )
    $networkHint = if ($localAddresses.Count) { $localAddresses -join ', ' } else { 'not found' }
    Write-Warning "Remote Ollama is not reachable. Dev PC IPv4: $networkHint. Put the GPU laptop and dev PC on the same Wi-Fi/router subnet, then check Ollama and firewall before generating a local_first proposal."
  }
}

Test-RemoteOllamaConnection

function Start-DevTerminal([string]$title, [string]$workingDirectory, [string]$command) {
  Start-Process powershell.exe -ArgumentList @(
    '-NoExit',
    '-Command',
    "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location -LiteralPath '$workingDirectory'; $command"
  )
}

function Test-DevPortListening([int]$port) {
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $connect = $client.ConnectAsync('127.0.0.1', $port)
    if (-not $connect.Wait(500)) { return $false }
    return $client.Connected
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

function Start-DevTerminalIfAvailable([string]$title, [string]$workingDirectory, [string]$command, [int]$port) {
  if (Test-DevPortListening $port) {
    Write-Host "$title is already listening on port $port; duplicate start skipped."
    return $false
  }
  Start-DevTerminal $title $workingDirectory $command
  return $true
}

# Bind every development server to the LAN interface for team testing.
$backendStarted = Start-DevTerminalIfAvailable "TOUR Backend $backendPort" (Join-Path $projectRoot 'backend') "& '$pythonPath' -m uvicorn app.main:app --reload --host 0.0.0.0 --port $backendPort" $backendPort
$aiStarted = Start-DevTerminalIfAvailable "TOUR AI $aiPort" $projectRoot "& '$pythonPath' -m uvicorn ai_server.app.main:app --reload --host 0.0.0.0 --port $aiPort" $aiPort
$frontendCommand = "`$env:VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:$backendPort'; `$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:$aiPort'; npm run dev -- --host 0.0.0.0 --port $frontendPort --strictPort"
$frontendStarted = Start-DevTerminalIfAvailable "TOUR Frontend $frontendPort" (Join-Path $projectRoot 'frontend') $frontendCommand $frontendPort

# /project-tree는 별도 Streamlit 앱을 iframe으로 표시하므로 개발 서버와 함께 시작한다.
# Streamlit이 아직 없는 PC에서는 나머지 세 서버를 막지 않고 설치 명령을 안내한다.
$projectTreeStarted = $false
& $pythonPath -c 'import streamlit' 2>$null
if ($LASTEXITCODE -eq 0) {
  $projectTreeCommand = "& '$pythonPath' -m streamlit run project_tree_explorer/app.py --server.address 0.0.0.0 --server.port $projectTreePort --server.headless true --browser.gatherUsageStats false"
  $projectTreeStarted = Start-DevTerminalIfAvailable "TOUR Project Tree $projectTreePort" $projectRoot $projectTreeCommand $projectTreePort
} else {
  Write-Warning "Project Tree was not started because Streamlit is missing. Install project_tree_explorer/requirements.txt, then run start-dev.ps1 again."
}

Write-Host "TP2-3 development services checked. New windows were opened only for ports that were not already listening."
Write-Host "Local URL: http://localhost:$frontendPort"
# Print a private LAN address for teammates. Keep this block ASCII-only because
# Windows PowerShell can misread UTF-8-without-BOM Korean text inside string literals.
$lanIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
  Sort-Object @{ Expression = { if ($_.InterfaceAlias -match 'Wi-Fi|Ethernet') { 0 } else { 1 } } } |
  Select-Object -First 1 -ExpandProperty IPAddress
if ($lanIp) {
  Write-Host "Team LAN URL: http://$lanIp`:$frontendPort"
} else {
  Write-Host "Team LAN URL: private IPv4 address was not found. Check ipconfig."
}
