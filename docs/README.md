# Материалы для публикаций

- `GasMeter_Pro_обзор.pdf` — обзорная статья о программе для корпоративной публикации
  и презентации: собирается `scripts/build_article_pdf.py` из текста и снимков экранов.
- `screens/print/` — снимки экранов, подготовленные под печать (300 dpi, палитра 256 цветов).
  Исходные снимки в полном разрешении в репозиторий не кладутся: они пересоздаются
  скриптом `scripts/capture_screens.py` со стенда.

Пересборка:

```bash
TOKEN=$(curl -s -X POST https://<стенд>/api/auth/login -H 'Content-Type: application/json' \
  -d '{"login":"...","password":"..."}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
python scripts/capture_screens.py --token "$TOKEN" --out docs/screens
python scripts/build_article_pdf.py
```
