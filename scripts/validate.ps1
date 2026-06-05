$ErrorActionPreference = 'Stop'

Write-Host '=== GasMeter Pro validation ===' -ForegroundColor Cyan

Write-Host '1/3 Backend tests' -ForegroundColor Cyan
Push-Location backend
try {
  if (-not (Test-Path '.venv')) {
    python -m venv .venv
  }
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  .\.venv\Scripts\python.exe -m pytest -q
}
finally {
  Pop-Location
}

Write-Host '2/3 Frontend build' -ForegroundColor Cyan
Push-Location frontend
try {
  npm install
  npm run build
}
finally {
  Pop-Location
}

Write-Host '3/3 Docker compose build' -ForegroundColor Cyan
docker compose -f compose.yaml build

Write-Host 'Validation completed successfully.' -ForegroundColor Green
