# Развёртывание ФОРВАТЕРА

Актуальный выпуск и границы проверки: [релиз 0.2.21](../docs/РЕЛИЗ_ФОРВАТЕР_0.2.21.md). Корпоративный сервер АРХИМЕД — `10.224.120.1:8840`; внешний стенд — адрес ниже. Обновление обоих контуров выполняется проверенным архивом Docker-образов после резервного копирования. Пример ручной сборки из исходников ниже сохранён для диагностики внешнего стенда, а не является протоколом последнего выпуска.

## Рабочий стенд (развёрнут)

**https://gasmeter.77-95-203-87.sslip.io** — внешний VPS `77.95.203.87`,
HTTPS от Let's Encrypt, открывается в том числе с телефона.

На сервере:

```text
/opt/gasmeter/
  docker-compose.yaml     запуск (frontend слушает 127.0.0.1:8090)
  .env                    GASMETER_DB_PASSWORD — пароль базы, права 600
  src/                    исходники версии, из которой собраны образы
  pgdata/                 данные PostgreSQL
  data/                   скан-копии МИ, протоколы, акты анализа газа
  mi_library/             библиотека сканов МИ
```

## База данных

Рабочая СУБД — **PostgreSQL 16** в отдельном контейнере `gasmeter-postgres-1`
(соседние сервисы сервера используют свои базы, смешивать не следует).
Локально и в тестах используется SQLite: движок выбирается переменной
`GASMETER_DATABASE_URL`, код от этого не зависит.

Резервная копия базы:

```bash
ssh -i ~/.ssh/personal_assistant_server root@77.95.203.87   "cd /opt/gasmeter && docker compose exec -T postgres pg_dump -U gasmeter gasmeter"   > backup/gasmeter-$(date +%Y%m%d).sql
```

Восстановление:

```bash
cat backup/gasmeter-YYYYMMDD.sql | ssh -i ~/.ssh/personal_assistant_server root@77.95.203.87   "cd /opt/gasmeter && docker compose exec -T postgres psql -U gasmeter -d gasmeter"
```

Перенос данных из SQLite (выполнен 03.09.2026, 781 строка) — на случай повторения:
`scripts/migrate_sqlite_to_postgres.py <путь к gasmeter.db>` при заданном
`GASMETER_DATABASE_URL`.

Наружу порт не публикуется: системный nginx проксирует
`gasmeter.77-95-203-87.sslip.io` → `127.0.0.1:8090`
(конфиг — `/etc/nginx/sites-available/gasmeter`, исходник в `deploy/nginx-gasmeter.conf`).

Соседние сервисы на этом же сервере — personal-assistant, БГИ МТР, ВРМ —
работают в своих контейнерах и папках и не затрагиваются.

Полная копия проекта и всех сканов МИ хранится на рабочем ПК:
`C:\projects\GasMeter` (сканы — `mi_library\raw`, 231 файл, 2 ГБ).

## Проверка поверок в ФГИС «Аршин»

В production Compose добавлен отдельный worker `arshin-checker`. Он сверяет
только конкретные физические СИ, добавленные метрологом или администратором
через раздел «Поверки в Аршине»; типовой каталог и демонстрационные номера не
опрашиваются. Сверка выполняется раз в сутки, при сетевой ошибке повторяется
через 15 минут. Требуется исходящий HTTPS-доступ к `fgis.gost.ru:443`.

Неполученный ответ отображается как «Источник недоступен», пустой результат
успешного запроса — как «Запись не найдена». Ни один из этих статусов не
подменяет сведения о поверке и не считается свидетельством. В текущей сети
VPS прямое соединение с ФГИС при проверке настройки завершилось тайм-аутом;
до открытия исходящего доступа фактическая сверка не подтверждена.

Список физических СИ должен быть заполнен по проверенной выгрузке ТОиР:
точный заводской номер и идентификацию экземпляра следует сверить с первичным
учётом до добавления.

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

## Корпоративный сервер «АРХИМЕД»

ФОРВАТЕР работает на `http://10.224.120.1:8840`. Инструкция для этого контура — [ARHIMED_DEPLOY.md](ARHIMED_DEPLOY.md); установленную версию, резервную копию и проверку после переключения фиксирует документ соответствующего релиза. Прежний адрес `10.61.157.1` относился к остановленной LLM и не является адресом АРХИМЕДа.
