$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
  $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if ([string]::IsNullOrWhiteSpace($pythonPath)) {
  throw 'Python was not found. Run setup-dev.ps1 first or install Python.'
}

& $pythonPath -m streamlit run project_tree_explorer/app.py --server.address 0.0.0.0 --server.port 8501
