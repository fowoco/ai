$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$uvicorn = Join-Path $root ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicorn)) {
    Write-Error "가상환경이 없습니다. 먼저: python -m venv .venv && .\.venv\Scripts\pip install -e `".[dev]`""
}

& $uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 @args
