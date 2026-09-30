# Сборка производственных образов GasMeter Pro и упаковка в архив для переноса
# на корпоративный сервер «Архимед» (10.224.120.1, без доступа в интернет:
# pip и npm там не работают, всё собирается в образ заранее).
#
# Запуск:  powershell -File deploy\build_bundle.ps1
# Результат: deploy\bundle\
#   gasmeter-images.tar.gz     — backend, frontend и postgres:16-alpine
#   docker-compose.yaml        — запуск на «Архимеде» (порт 127.0.0.1:8840)
#   ARHIMED_DEPLOY.md          — порядок установки и проверки
#   backup.sh                  — ежедневная копия базы (cron gasmeter-backup)
#   SHA256SUMS                 — контрольные суммы всего комплекта

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$bundle = "$PSScriptRoot\bundle"

docker build -t gasmeter-backend:latest "$root\backend"
if (-not $?) { throw 'backend image build failed' }

docker build -t gasmeter-frontend:latest --build-arg NGINX_CONF=nginx.prod.conf --build-arg VITE_API_BASE= "$root\frontend"
if (-not $?) { throw 'frontend image build failed' }

# База данных тоже едет файлом: на сервере нет реестра образов
docker pull postgres:16-alpine
if (-not $?) { throw 'postgres image pull failed' }

New-Item -ItemType Directory -Force $bundle | Out-Null
docker save gasmeter-backend:latest gasmeter-frontend:latest postgres:16-alpine | gzip -c > "$bundle\gasmeter-images.tar.gz"
if (-not $?) { throw 'docker save failed' }

Copy-Item "$PSScriptRoot\docker-compose.arhimed.yaml" "$bundle\docker-compose.yaml" -Force
Copy-Item "$PSScriptRoot\ARHIMED_DEPLOY.md" "$bundle\ARHIMED_DEPLOY.md" -Force
Copy-Item "$PSScriptRoot\backup.sh" "$bundle\backup.sh" -Force

Push-Location $bundle
Get-ChildItem -File | Where-Object { $_.Name -ne 'SHA256SUMS' } | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Set-Content -Encoding ascii SHA256SUMS
Pop-Location

$size = (Get-Item "$bundle\gasmeter-images.tar.gz").Length / 1MB
Write-Host ("Комплект готов: deploy\bundle\ (образы {0:N0} МБ)" -f $size)
