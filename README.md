# CRM

سامانه فارسی و راست‌به‌چپ مدیریت مشتریان، فروش‌ها و فعالیت‌ها.

- سند نیازمندی‌ها: [docs/crm-product-spec.fa.md](docs/crm-product-spec.fa.md)
  - تصمیم‌های قطعی محصول: بخش ۰
  - قواعدی که هنگام پیاده‌سازی انتخاب شده‌اند: بخش ۰٫۱
  - وضعیت پیاده‌سازی و کارهای باقی‌مانده: بخش ۱۷
- استخراج تصاویر مرجع: [docs/crm-image-observations.fa.md](docs/crm-image-observations.fa.md)
- دامنه انتشار اول: هسته فروش

## امکانات فعلی

- ورود با کد یک‌بارمصرف پنج‌رقمی (پیامک یا ایمیل) و نشست JWT
- مشتریان احتمالی، مشتریان و سازمان‌ها؛ تشخیص تکرار و تبدیل سرنخ به مشتری
- فروش‌ها، تابلوی فروش با کشیدن و رهاکردن، نتیجه نهایی، پرداخت و مانده دریافت‌نشده
- فعالیت‌ها، تقویم روز/هفته/ماه، یادداشت و سابقه پیگیری هر پرونده
- نمای کلی و گزارش‌ها
- تنظیمات: کاربران، تیم‌ها، مراحل فروش، منابع جذب و سوابق ممیزی
- دسترسی در سه سطح ادمین، مدیر فروش و کارشناس؛ کارشناس از پرونده‌های دیگران فقط وضعیت فعلی را می‌بیند

## ساختار

| مسیر | توضیح |
| --- | --- |
| `apps/web` | Next.js، shadcn/ui، Tailwind CSS، فونت وزیرمتن، تاریخ شمسی |
| `apps/api` | FastAPI، SQLAlchemy، Alembic |
| `apps/api/app/modules` | `auth`، `identity` (کاربران و تیم‌ها)، `audit`، `crm` (مشتری و سرنخ)، `sales` (فروش و پرداخت)، `activities`، `reports` |
| `docker-compose.yml` | PostgreSQL، Redis و RabbitMQ برای توسعه محلی |
| `docs/` | سند نیازمندی‌ها؛ تصاویر طراحی و مرجع فقط محلی نگهداری می‌شوند و وارد Git نمی‌شوند |

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

ثبت‌نام عمومی وجود ندارد. اولین ادمین با دستور `create-user` ساخته می‌شود (نقش‌ها: `admin`، `sales_manager`، `sales_rep`)؛ بقیه کاربران و تیم‌ها از صفحه «تنظیمات» مدیریت می‌شوند.

برای ورود در محیط توسعه، شماره یا ایمیل کاربر را در http://localhost:3000/login وارد کنید؛ کد پنج‌رقمی فقط در لاگ API (خط `DEV OTP`) چاپ می‌شود. این ارسال‌کننده در سایر محیط‌ها غیرفعال است. اگر در آزمون‌های مکرر به سقف درخواست کد رسیدید، شمارنده‌های محلی را پاک کنید:

```bash
docker compose exec redis sh -c "redis-cli --scan --pattern 'otp:*' | xargs -r redis-cli del"
```

اگر پورتی روی سیستم شما اشغال است، `CRM_POSTGRES_PORT`، `CRM_REDIS_PORT` یا `CRM_RABBITMQ_PORT` را هنگام اجرای Docker Compose تغییر دهید و `CRM_DATABASE_URL` را مطابق آن تنظیم کنید.

## بررسی‌ها

همان بررسی‌های CI:

```bash
cd apps/web && pnpm lint && pnpm typecheck && pnpm build
cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run mypy app tests && uv run pytest
```

آزمون‌های API روی پایگاه داده جداگانه `crm_test` و Redis شماره ۱۵ اجرا می‌شوند و به داده محیط توسعه دست نمی‌زنند.

## نکته امنیتی

این مخزن عمومی است. هیچ اعتبارنامه، کلید سرویس یا داده واقعی مشتری وارد مخزن نمی‌شود؛ اسرار فقط در GitHub Secrets و تنظیمات میزبان نگهداری می‌شوند. در محیط آزمایشی و تولید، `CRM_JWT_SECRET` و `CRM_OTP_SECRET` باید تنظیم شوند؛ در غیر این صورت API اجرا نمی‌شود.
