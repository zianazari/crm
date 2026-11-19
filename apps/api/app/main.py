from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.modules.activities import router as activities
from app.modules.activities import team_tasks, timeline
from app.modules.audit import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.sender import SenderNotConfiguredError
from app.modules.automation import router as automation
from app.modules.campaigns import direct
from app.modules.campaigns import router as campaigns
from app.modules.crm import customers, leads, organizations, reference
from app.modules.identity import router as identity_router
from app.modules.messaging import router as messaging
from app.modules.notifications import router as notifications
from app.modules.reports import router as reports
from app.modules.sales import deals, stages


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CRM API",
        version="0.1.0",
        # Interactive docs only outside production.
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Fail closed: if Redis (OTP, rate limits, session revocation) is unavailable,
    # authentication is refused rather than skipped (spec section 8).
    @app.exception_handler(RedisError)
    def redis_unavailable(_: Request, __: RedisError) -> JSONResponse:
        return JSONResponse(
            {"detail": "سرویس موقتاً در دسترس نیست. کمی بعد دوباره تلاش کنید."}, status_code=503
        )

    @app.exception_handler(SenderNotConfiguredError)
    def sender_missing(_: Request, __: SenderNotConfiguredError) -> JSONResponse:
        return JSONResponse({"detail": "ارسال کد ورود هنوز پیکربندی نشده است."}, status_code=503)

    app.include_router(auth_router)
    for module in (
        leads,
        customers,
        organizations,
        reference,
        deals,
        stages,
        activities,
        timeline,
        team_tasks,
        reports,
        identity_router,
        audit_router,
        messaging,
        notifications,
        automation,
        campaigns,
    ):
        app.include_router(module.router)
    app.include_router(campaigns.suppressions)
    app.include_router(direct.templates)
    app.include_router(direct.router)
    app.include_router(campaigns.public)
    app.include_router(messaging.webhooks)

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        """The process is up. Does not touch dependencies."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        """The API can serve traffic: the database answers."""
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable", "database": "down"}
        return {"status": "ok", "database": "up"}

    return app


app = create_app()
