# Развёртывание GasMeter Pro

## Рабочий стенд (развёрнут)

**https://gasmeter.77-95-203-87.sslip.io** — внешний VPS `77.95.203.87`,
HTTPS от Let's Encrypt, открывается в том числе с телефона.

На сервере:

```text
/opt/gasmeter/
  docker-compose.yaml     запуск (frontend слушает 127.0.0.1:8090)
  src/                    исходники версии, из которой собраны образы
  data/                   SQLite, скан-копии МИ, протоколы (сохраняется при обновлении)
  mi_library/             библиотека сканов МИ
```

Наружу порт не публикуется: системный nginx проксирует
`gasmeter.77-95-203-87.sslip.io` → `127.0.0.1:8090`
(конфиг — `/etc/nginx/sites-available/gasmeter`, исходник в `deploy/nginx-gasmeter.conf`).

Соседние сервисы на этом же сервере — personal-assistant, БГИ МТР, ВРМ —
работают в своих контейнерах и папках и не затрагиваются.

Полная копия проекта и всех сканов МИ хранится на рабочем ПК:
`C:\projects\GasMeter` (сканы — `mi_library\raw`, 231 файл, 2 ГБ).

## Обновление версии

С рабочего ПК:

```bash
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='mi_library' --exclude='dist' --exclude='backend/data' -czf /tmp/gasmeter-src.tar.gz .
scp -i ~/.ssh/personal_assistant_server /tmp/gasmeter-src.tar.gz root@77.95.203.87:/opt/gasmeter/
```

На сервере:

```bash
cd /opt/gasmeter/src && tar xzf ../gasmeter-src.tar.gz
docker build -t gasmeter-backend:latest backend
docker build -t gasmeter-frontend:latest --build-arg NGINX_CONF=nginx.prod.conf frontend
cd /opt/gasmeter && docker compose up -d
curl -s http://127.0.0.1:8090/health
```

База и сканы при обновлении сохраняются — они в volume `./data` и `./mi_library`.

## Проверка состояния

```bash
ssh -i ~/.ssh/personal_assistant_server root@77.95.203.87 "cd /opt/gasmeter && docker compose ps && curl -s http://127.0.0.1:8090/health"
```

Логи: `docker compose logs -f backend` (или `frontend`) в `/opt/gasmeter`.

## Резервное копирование

Забрать базу и документы на рабочий ПК:

```bash
scp -i ~/.ssh/personal_assistant_server -r root@77.95.203.87:/opt/gasmeter/data backup/gasmeter-data-$(date +%Y%m%d)
```

## Альтернатива: корпоративный сервер «Архимед» (10.61.157.1)

Доступен только через провод, с привязкой исходящего адреса:
`ssh -b <IP_провода> -i ~/.ssh/personal_assistant_server ...`.
На момент развёртывания порт 22 с рабочего места не отвечал, поэтому стенд
поднят на внешнем VPS. Для переноса: собрать образы (`deploy/build_bundle.ps1`),
перенести `deploy/bundle/gasmeter-images.tar`, `docker load`, затем
`docker compose up -d` по той же схеме.
