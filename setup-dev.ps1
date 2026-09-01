<#
  새 PC에서 TP2-3 개발 환경을 처음 준비하는 스크립트입니다.
  Git으로 내려받지 않는 Python 가상환경·node_modules·.env만 만들며,
  API 키·MySQL 비밀번호·관광 원본 데이터는 절대 복사하거나 생성하지 않습니다.
#>

[CmdletBinding()]
param(
  # 이미 설치된 패키지를 다시 확인하고 싶을 때 사용합니다.
  [switch]$Refresh
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot 'backend\.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$requirementsPath = Join-Path $projectRoot 'requirements.txt'
$frontendPath = Join-Path $projectRoot 'frontend'
$envExamplePath = Join-Path $projectRoot '.env.example'
$envPath = Join-Path $projectRoot '.env'

function Write-SetupStep([string]$message) {
  "`n==> $message" | Write-Host -ForegroundColor Cyan
}

function Stop-Setup([string]$message) {
  Write-Host "`n[설치 중단] $message" -ForegroundColor Red
  exit 1
}

# 새 PC에서는 Python 설치가 필요하지만, 이미 만든 가상환경이 있다면 PATH의 Python 없이도 재실행할 수 있습니다.
$hasVirtualEnvironment = Test-Path -LiteralPath $venvPython
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand -and -not $hasVirtualEnvironment) {
  # Windows Python Launcher만 설치된 경우도 지원합니다.
  $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCommand -and -not $hasVirtualEnvironment) {
  Stop-Setup 'Python을 찾지 못했습니다. Python 3.10 이상을 설치한 뒤 VS Code를 다시 열어 주세요.'
}

Write-SetupStep 'Python 버전 확인'
if ($hasVirtualEnvironment) {
  $pythonVersionText = (& $venvPython --version).Trim()
} else {
  $pythonVersionText = (& $pythonCommand.Source --version).Trim()
}
$pythonVersionText | Write-Host
if ($pythonVersionText -notmatch '(\d+)\.(\d+)') {
  Stop-Setup 'Python 버전을 확인하지 못했습니다. Python 3.10 이상을 설치해 주세요.'
}
if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 10)) {
  Stop-Setup 'Python 3.10 이상이 필요합니다.'
}

# Vite 8과 현재 lock 파일은 Node 20.19 이상 또는 Node 22.12 이상을 요구합니다.
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm -ErrorAction SilentlyContinue
if (-not $nodeCommand -or -not $npmCommand) {
  Stop-Setup 'Node.js와 npm을 찾지 못했습니다. Node.js 20.19 이상(LTS 권장)을 설치한 뒤 다시 실행해 주세요.'
}
Write-SetupStep 'Node.js 버전 확인'
$nodeVersionText = (& $nodeCommand.Source --version).Trim()
$nodeVersionText | Write-Host
if ($nodeVersionText -notmatch 'v?(\d+)\.(\d+)\.(\d+)') {
  Stop-Setup 'Node.js 버전을 확인하지 못했습니다. Node.js 20.19 이상 또는 22.12 이상을 설치해 주세요.'
}
$nodeMajor = [int]$Matches[1]
$nodeMinor = [int]$Matches[2]
$nodePatch = [int]$Matches[3]
$node20Supported = $nodeMajor -eq 20 -and ($nodeMinor -gt 19 -or ($nodeMinor -eq 19 -and $nodePatch -ge 0))
$node22Supported = $nodeMajor -eq 22 -and ($nodeMinor -gt 12 -or ($nodeMinor -eq 12 -and $nodePatch -ge 0))
if (-not ($node20Supported -or $node22Supported -or $nodeMajor -gt 22)) {
  Stop-Setup '이 프로젝트의 Vite 8은 Node.js 20.19 이상 또는 22.12 이상이 필요합니다.'
}

# 가상환경은 PC별로 만드는 파일이므로 Git에 포함하지 않습니다.
if (-not $hasVirtualEnvironment) {
  Write-SetupStep 'Python 가상환경 생성 (backend/.venv)'
  & $pythonCommand.Source -m venv $venvPath
} else {
  Write-Host '기존 Python 가상환경을 사용합니다.' -ForegroundColor DarkGray
}

# requirements.txt는 Backend와 AI Server가 공유하는 Python 패키지 목록입니다.
if ($Refresh -or -not (Test-Path -LiteralPath (Join-Path $venvPath 'Lib\site-packages\fastapi'))) {
  Write-SetupStep 'Python 패키지 설치 (requirements.txt)'
  & $venvPython -m pip install --upgrade pip
  & $venvPython -m pip install -r $requirementsPath
} else {
  Write-Host 'Python 패키지가 이미 설치되어 있습니다. 다시 설치하려면 .\setup-dev.ps1 -Refresh 를 사용하세요.' -ForegroundColor DarkGray
}

# package-lock.json을 기준으로 설치해 팀원마다 같은 프론트엔드 의존성 버전을 받습니다.
if ($Refresh -or -not (Test-Path -LiteralPath (Join-Path $frontendPath 'node_modules'))) {
  Write-SetupStep '프론트엔드 패키지 설치 (package-lock.json)'
  Push-Location $frontendPath
  try {
    & $npmCommand.Source ci
  } finally {
    Pop-Location
  }
} else {
  Write-Host 'frontend/node_modules를 사용합니다. 다시 설치하려면 .\setup-dev.ps1 -Refresh 를 사용하세요.' -ForegroundColor DarkGray
}

# .env는 개인별 비밀 설정 파일입니다. 기존 팀원의 값을 절대 덮어쓰지 않습니다.
if (-not (Test-Path -LiteralPath $envPath)) {
  Write-SetupStep '.env 예시 파일 생성'
  Copy-Item -LiteralPath $envExamplePath -Destination $envPath
  Write-Host '.env를 만들었습니다. OpenAI·지도·MySQL 키는 팀에서 안전하게 전달받아 직접 입력하세요.' -ForegroundColor Yellow
} else {
  Write-Host '기존 .env를 유지합니다.' -ForegroundColor DarkGray
}

# 원본 데이터는 라이선스·용량 때문에 Git에서 제외합니다. 실제 파일이 없으면 숫자를 임의로 표시하지 않습니다.
$rawDataPath = Join-Path $projectRoot 'data\raw'
$rawFiles = @(
  Get-ChildItem -LiteralPath $rawDataPath -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.zip', '.csv', '.xlsx', '.xls' }
)
if ($rawFiles.Count -eq 0) {
  Write-Host '주의: data/raw에 실제 관광 원본 파일이 없습니다. 팀 공유 드라이브의 원본 데이터 묶음을 같은 경로에 복사해 주세요.' -ForegroundColor Yellow
} else {
  Write-Host "관광 원본 파일 $($rawFiles.Count)개를 확인했습니다." -ForegroundColor Green
}

Write-Host "`n설치가 끝났습니다. 아래 명령으로 세 서버를 실행하세요:" -ForegroundColor Green
Write-Host '  .\start-dev.ps1' -ForegroundColor White
Write-Host '브라우저: http://localhost:5176' -ForegroundColor White
