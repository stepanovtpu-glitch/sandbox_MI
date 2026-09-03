#!/bin/sh
# Резервное копирование GasMeter Pro.
#
# Сохраняет дамп PostgreSQL и файлы, которых нет в базе: скан-копии МИ,
# акты лабораторного анализа и сформированные протоколы. Запускается по cron
# ежедневно; старые копии удаляются по сроку хранения.
#
# Установка на сервере:
#   cp /opt/gasmeter/src/deploy/backup.sh /opt/gasmeter/backup.sh && chmod +x /opt/gasmeter/backup.sh
#   crontab -l | { cat; echo "30 2 * * * /opt/gasmeter/backup.sh >> /opt/gasmeter/backup/backup.log 2>&1"; } | crontab -

set -eu

ROOT=/opt/gasmeter
BACKUP_DIR="$ROOT/backup"
KEEP_DAYS=${GASMETER_BACKUP_KEEP_DAYS:-14}
STAMP=$(date +%Y%m%d_%H%M)
DUMP="$BACKUP_DIR/db_$STAMP.sql.gz"

mkdir -p "$BACKUP_DIR"
cd "$ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] начало резервного копирования"

# 1. База данных
docker compose exec -T postgres pg_dump -U gasmeter --clean --if-exists gasmeter | gzip > "$DUMP"

# Пустой или обрезанный дамп хуже отсутствующего: он создаёт ложное чувство
# защищённости, поэтому проверяем размер и читаемость сразу после создания.
SIZE=$(stat -c %s "$DUMP")
if [ "$SIZE" -lt 10240 ]; then
    echo "ОШИБКА: дамп подозрительно мал ($SIZE байт), копия удалена"
    rm -f "$DUMP"
    exit 1
fi
if ! gzip -t "$DUMP" 2>/dev/null; then
    echo "ОШИБКА: архив дампа повреждён, копия удалена"
    rm -f "$DUMP"
    exit 1
fi

# 2. Документы: акты анализа газа и скан-копии, приложенные к версиям МИ
if [ -d "$ROOT/data" ]; then
    tar czf "$BACKUP_DIR/files_$STAMP.tar.gz" -C "$ROOT" \
        --exclude='data/*.db' --exclude='data/*.db.*' data 2>/dev/null || true
fi

# 3. Ротация
find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'files_*.tar.gz' -mtime "+$KEEP_DAYS" -delete

TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
COUNT=$(find "$BACKUP_DIR" -name 'db_*.sql.gz' | wc -l)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] готово: $(basename "$DUMP") ($((SIZE / 1024)) КБ); копий базы: $COUNT; всего: $TOTAL"
