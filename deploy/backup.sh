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
umask 077

ROOT=/opt/gasmeter
BACKUP_DIR="$ROOT/backup"
KEEP_DAYS=${GASMETER_BACKUP_KEEP_DAYS:-14}
STAMP=$(date +%Y%m%d_%H%M%S)_$$
DUMP="$BACKUP_DIR/db_$STAMP.sql.gz"
FILES="$BACKUP_DIR/files_$STAMP.tar.gz"
RAW_DUMP="$BACKUP_DIR/.db_$STAMP.sql"
DUMP_PART="$BACKUP_DIR/.db_$STAMP.sql.gz"
FILES_PART="$BACKUP_DIR/.files_$STAMP.tar.gz"
PUBLISHED=0

mkdir -p "$BACKUP_DIR"
if [ -e "$DUMP" ] || [ -e "$FILES" ]; then
    echo "ОШИБКА: архив с таким идентификатором уже существует"
    exit 1
fi

cleanup() {
    rm -f "$RAW_DUMP" "$DUMP_PART" "$FILES_PART"
    if [ "$PUBLISHED" -eq 0 ]; then
        rm -f "$DUMP" "$FILES"
    fi
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

cd "$ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] начало резервного копирования"

# 1. База данных
docker compose exec -T postgres pg_dump -U gasmeter --clean --if-exists gasmeter > "$RAW_DUMP"

# Пустой или обрезанный дамп хуже отсутствующего: он создаёт ложное чувство
# защищённости, поэтому проверяем размер и читаемость сразу после создания.
RAW_SIZE=$(stat -c %s "$RAW_DUMP")
if [ "$RAW_SIZE" -lt 10240 ]; then
    echo "ОШИБКА: дамп подозрительно мал ($RAW_SIZE байт)"
    exit 1
fi
gzip -c "$RAW_DUMP" > "$DUMP_PART"
if ! gzip -t "$DUMP_PART" 2>/dev/null; then
    echo "ОШИБКА: архив дампа повреждён"
    exit 1
fi
SIZE=$(stat -c %s "$DUMP_PART")

# 2. Документы: акты анализа газа и скан-копии, приложенные к версиям МИ
if [ ! -d "$ROOT/data" ]; then
    echo "ОШИБКА: каталог документов отсутствует"
    exit 1
fi
tar czf "$FILES_PART" -C "$ROOT" \
    --exclude='data/*.db' --exclude='data/*.db.*' data
if ! tar tzf "$FILES_PART" > /dev/null; then
    echo "ОШИБКА: архив документов повреждён"
    exit 1
fi
mv "$DUMP_PART" "$DUMP"
mv "$FILES_PART" "$FILES"
PUBLISHED=1

# 3. Ротация
find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'files_*.tar.gz' -mtime "+$KEEP_DAYS" -delete

TOTAL=$(du -sh "$BACKUP_DIR" | cut -f1)
COUNT=$(find "$BACKUP_DIR" -name 'db_*.sql.gz' | wc -l)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] готово: $(basename "$DUMP") ($((SIZE / 1024)) КБ); копий базы: $COUNT; всего: $TOTAL"
