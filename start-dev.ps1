$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$backendPort = 8100
$aiPort = 8111
$frontendPort = 5176

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

# Bind every development server to the LAN interface for team testing.
Start-DevTerminal "TOUR Backend $backendPort" (Join-Path $projectRoot 'backend') "& '$pythonPath' -m uvicorn app.main:app --reload --host 0.0.0.0 --port $backendPort"
Start-DevTerminal "TOUR AI $aiPort" $projectRoot "& '$pythonPath' -m uvicorn ai_server.app.main:app --reload --host 0.0.0.0 --port $aiPort"
$frontendCommand = "`$env:VITE_BACKEND_PROXY_TARGET='http://127.0.0.1:$backendPort'; `$env:VITE_AI_PROXY_TARGET='http://127.0.0.1:$aiPort'; npm run dev -- --host 0.0.0.0 --port $frontendPort --strictPort"
Start-DevTerminal "TOUR Frontend $frontendPort" (Join-Path $projectRoot 'frontend') $frontendCommand

Write-Host "TP2-3 Backend $backendPort, AI Server $aiPort, and Frontend $frontendPort started in separate windows."
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
