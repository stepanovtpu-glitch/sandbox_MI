# Сборка производственных образов GasMeter Pro и упаковка в архив для переноса
# на корпоративный сервер «Архимед» (без доступа сервера в интернет).
#
# Запуск:  powershell -File deploy\build_bundle.ps1
# Результат: deploy\bundle\gasmeter-images.tar (+ docker-compose.prod.yaml)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent

docker build -t gasmeter-backend:latest "$root\backend"
if (-not $?) { throw 'backend image build failed' }

docker build -t gasmeter-frontend:latest --build-arg NGINX_CONF=nginx.prod.conf --build-arg VITE_API_BASE= "$root\frontend"
if (-not $?) { throw 'frontend image build failed' }

New-Item -ItemType Directory -Force "$PSScriptRoot\bundle" | Out-Null
docker save -o "$PSScriptRoot\bundle\gasmeter-images.tar" gasmeter-backend:latest gasmeter-frontend:latest
if (-not $?) { throw 'docker save failed' }
Copy-Item "$PSScriptRoot\docker-compose.prod.yaml" "$PSScriptRoot\bundle\docker-compose.yaml" -Force

$size = (Get-Item "$PSScriptRoot\bundle\gasmeter-images.tar").Length / 1MB
Write-Host ("Bundle готов: deploy\bundle\gasmeter-images.tar ({0:N0} МБ)" -f $size)
