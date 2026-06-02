# GasMeter Pro

Автоматизированная система расчёта суммарной погрешности и подбора методик измерений узлов учёта газа.

Проект создаётся по ТЗ-GASMETER-PRO-2026: конструктор измерительной линии, база средств измерений, расчёт δΣ по методу квадратурного суммирования, библиотека МИ, скоринг применимости методик, рекомендации по замене СИ и формирование протоколов расчёта.

## Текущий статус

Инициализирован каркас MVP:

- backend: FastAPI + SQLite + расчётное ядро на Python;
- frontend: React + TypeScript + Vite;
- единая модель данных для СИ, МИ и расчёта;
- базовая формула δΣ;
- API для health-check и расчёта погрешности;
- промышленный dark UI в стиле Industrial Precision Dashboard.

## Быстрый запуск

### Backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API будет доступен на `http://127.0.0.1:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI будет доступен на `http://127.0.0.1:5173`.

## Целевой стек

- React 18 + TypeScript;
- FastAPI;
- SQLite для offline-режима;
- Python 3.11;
- последующая упаковка в Electron.

## Приоритет разработки

1. Расчётное ядро δΣ.
2. Конструктор измерительной линии.
3. База СИ и импорт Excel/CSV.
4. Библиотека МИ и скоринг.
5. Подбор альтернативных СИ.
6. Экспорт PDF/DOCX.
7. Electron/offline-режим.
