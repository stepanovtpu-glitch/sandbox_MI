#!/usr/bin/env bash
set -euo pipefail

echo '=== GasMeter Pro validation ==='

echo '1/3 Backend tests'
cd backend
if [ ! -d '.venv' ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
deactivate
cd ..

echo '2/3 Frontend build'
cd frontend
npm install
npm run build
cd ..

echo '3/3 Docker compose build'
docker compose -f compose.yaml build

echo 'Validation completed successfully.'
