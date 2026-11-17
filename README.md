# CRM

سامانه فارسی و راست‌به‌چپ مدیریت مشتریان، فروش‌ها و فعالیت‌ها.

- سند نیازمندی‌ها: [docs/crm-product-spec.fa.md](docs/crm-product-spec.fa.md) (تصمیم‌های قطعی در بخش ۰)
- دامنه انتشار اول: هسته فروش

## ساختار

| مسیر | توضیح |
| --- | --- |
| `apps/web` | Next.js، shadcn/ui، Tailwind CSS، فونت وزیرمتن |
| `apps/api` | FastAPI، SQLAlchemy، Alembic |
| `docker-compose.yml` | PostgreSQL، Redis و RabbitMQ برای توسعه محلی |

## اجرای محلی

پیش‌نیازها: Docker، Node.js 24 با pnpm و [uv](https://docs.astral.sh/uv/).

```bash
# سرویس‌های محلی (Postgres روی پورت 5432)
docker compose up -d --wait

# API: http://localhost:8000/docs
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.cli create-user --name "نام شما" --mobile 09xxxxxxxxx --role admin
uv run uvicorn app.main:app --reload

# وب: http://localhost:3000
cd apps/web
pnpm install
pnpm dev
```

برای ورود در محیط توسعه، شماره یا ایمیل کاربر ساخته‌شده را در http://localhost:3000/login وارد کنید؛ کد پنج‌رقمی فقط در لاگ API (خط `DEV OTP`) چاپ می‌شود. این ارسال‌کننده در سایر محیط‌ها غیرفعال است.

اگر پورتی روی سیستم شما اشغال است، `CRM_POSTGRES_PORT`، `CRM_REDIS_PORT` یا `CRM_RABBITMQ_PORT` را هنگام اجرای Docker Compose تغییر دهید و `CRM_DATABASE_URL` را مطابق آن تنظیم کنید.

## بررسی‌ها

همان بررسی‌های CI:

```bash
cd apps/web && pnpm lint && pnpm typecheck && pnpm build
cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run mypy app tests && uv run pytest
```

## نکته امنیتی

این مخزن عمومی است. هیچ اعتبارنامه، کلید سرویس یا داده واقعی مشتری وارد مخزن نمی‌شود؛ اسرار فقط در GitHub Secrets و تنظیمات میزبان نگهداری می‌شوند. تصاویر طراحی و مرجع فقط به‌صورت محلی نگهداری می‌شوند.
