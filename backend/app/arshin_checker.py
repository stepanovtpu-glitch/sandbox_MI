"""Отдельный worker ежедневной сверки зарегистрированных СИ с ФГИС «Аршин»."""
from __future__ import annotations

import logging
import os
import time

from app.arshin_monitor import check_due_assets
from app.database import init_db

logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger('gasmeter.arshin_checker')


def main() -> None:
    interval = max(15, int(os.environ.get('GASMETER_ARSHIN_WORKER_INTERVAL_SECONDS', '60')))
    init_db()
    logger.info('Arshin checker started; cadence=%ss', interval)
    while True:
        try:
            checked = check_due_assets()
            if checked:
                logger.info('Completed due Arshin checks: %s', checked)
        except Exception as error:  # noqa: BLE001 — цикл должен переживать временный сбой БД/сервиса
            logger.error('Arshin check cycle failed (%s)', error.__class__.__name__)
        time.sleep(interval)


if __name__ == '__main__':
    main()
