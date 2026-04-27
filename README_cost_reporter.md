# Daily Cost Reporter

Модуль `cost_reporter` збирає щоденні витрати з кількох провайдерів (OpenAI, Railway, Google Cloud) і надсилає один агрегований звіт у Telegram.

## Архітектура

```text
cost_reporter/
  __init__.py
  main.py
  config.py
  telegram.py
  registry.py
  providers/
    __init__.py
    base.py
    openai_provider.py
    railway_provider.py
    google_cloud_provider.py
```

- `providers/base.py` — контракт `CostProvider` та модель `CostResult`.
- `registry.py` — фабрика провайдерів із `COST_PROVIDERS`.
- `main.py` — CLI entrypoint + orchestration (`asyncio.gather`, fault isolation).
- `telegram.py` — форматування і відправка звіту через Telegram Bot API.
- кожен provider повертає `ok|warning|error|skipped`, не валить весь репорт.

## Env variables

### Core
- `COST_PROVIDERS=openai,railway,google_cloud`

### Telegram
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### OpenAI
- `OPENAI_ADMIN_KEY`
- `OPENAI_COST_GROUP_BY` (optional, напр. `project_id,line_item`)

### Railway
- `RAILWAY_API_TOKEN`
- `RAILWAY_TEAM_ID` (optional)
- `RAILWAY_PROJECT_ID` (optional)

### Google Cloud (BigQuery billing export)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` **або** `GOOGLE_APPLICATION_CREDENTIALS_JSON_B64` **або** `GOOGLE_APPLICATION_CREDENTIALS`
- `GCP_BILLING_PROJECT_ID`
- `GCP_BILLING_TABLE`

## Локальний запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# відредагуйте .env
python -m cost_reporter.main --date yesterday --dry-run
python -m cost_reporter.main --date 2026-04-27 --dry-run
```

Без `--dry-run` модуль відправляє повідомлення в Telegram.

## Railway запуск (MVP)

### Файли для Railway deploy

У репозиторій додано:
- `railway.json` — базова конфігурація build/deploy для Railway.
- `nixpacks.toml` — мінімальний start command для Railway/Nixpacks без ручного втручання в python/pip середовище.
- `Procfile` — worker fallback command (`python -m cost_reporter.main --date yesterday`).

### One-off command
```bash
python -m cost_reporter.main --date yesterday
```

### Railway Cron приклад
- Schedule: `0 7 * * *` (щодня о 07:00 UTC)
- Command:
```bash
python -m cost_reporter.main --date yesterday
```

### Налаштування в Railway
1. Підключіть репозиторій до Railway Project.
2. Додайте всі змінні з `.env.example` у Variables (без значень-заглушок).
3. Для щоденного запуску створіть Railway Cron Job з командою:
   `python -m cost_reporter.main --date yesterday`
4. Рекомендований schedule: `0 7 * * *` (UTC).


## OpenClaw cron command (приклад)

```bash
python -m cost_reporter.main --date yesterday
```

> У вашій OpenClaw конфігурації Telegram already enabled, тому головне — коректні env для cost providers.

## Як додати нового provider

1. Створіть новий файл у `cost_reporter/providers/`, наприклад `my_provider.py`.
2. Реалізуйте клас, успадкований від `CostProvider` з методом `get_daily_cost(start_date, end_date)`.
3. Зареєструйте його в `cost_reporter/registry.py`.
4. Додайте назву в `COST_PROVIDERS`.

## Troubleshooting

- `status=skipped`: не вистачає env — перевірте `.env` / Railway Variables.
- `OpenAI error`: перевірте, що `OPENAI_ADMIN_KEY` має доступ до Organization Costs API.
- `Railway warning`: GraphQL schema може відрізнятися; оновіть query у `railway_provider.py` (є TODO).
- `Google Cloud error`: перевірте BigQuery Billing Export table, IAM права service account і project/table IDs.
- Якщо використовуєте B64, перевірте валідність `GOOGLE_APPLICATION_CREDENTIALS_JSON_B64` (base64 від повного JSON ключа).
- Якщо Railway build падає на `externally-managed-environment`, не запускайте `ensurepip`; залишайте `nixpacks.toml` мінімальним (тільки `[start]`).
- `Telegram send failed`: перевірте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, чи бот доданий у канал/чат.

## Security notes

- Не зберігайте логіни/паролі у коді чи git.
- Не логуйте секрети (tokens, keys, service account private key).
- Використовуйте API keys і service accounts.
- Browser automation для billing — тільки крайній варіант; пріоритет офіційним API/експортам.
