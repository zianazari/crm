"""Running campaigns (spec 4.5; criteria 8, 10, 11).

The worker calls ``tick`` every few seconds. Under a Postgres advisory lock (held on
its own connection, since every batch commits) it:

1. starts scheduled campaigns whose time has come, fixing their recipient list;
2. for each running campaign, queues the next batch, if the sending window, the daily
   limit and the 30-day budget allow, checking each recipient again just before;
3. finishes campaigns with nobody left to queue once their messages have a final
   status (completed, or failed when not one message was accepted).

Queuing a recipient and creating their message happen in one transaction, with the
recipient row locked, so a recipient never gets two messages.
"""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.campaigns import audience as aud
from app.modules.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignStatus,
    DirectMessage,
    MessagingPolicy,
    RecipientStatus,
    Suppression,
)
from app.modules.crm.access import build_scope
from app.modules.crm.models import Customer, Lead
from app.modules.messaging.models import (
    FINAL_STATUSES,
    Channel,
    MessageStatus,
    OutboundMessage,
    Purpose,
)
from app.modules.messaging.service import enqueue
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import fa, notify

logger = logging.getLogger("crm.campaigns")

ADVISORY_LOCK = 0x43524D5F43414D  # "CRM_CAM"
BATCH = 50
SUCCESS = {MessageStatus.ACCEPTED, MessageStatus.DELIVERED}


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def policy(db: Session) -> MessagingPolicy:
    row = db.get(MessagingPolicy, 1)
    if row is None:
        row = MessagingPolicy(id=1)
        db.add(row)
        db.flush()
    return row


def hhmm(value: time) -> str:
    return fa(value.strftime("%H:%M"))


# -- the recipient list ----------------------------------------------------------------


def snapshot(db: Session, campaign: Campaign) -> int:
    """Fixes who the campaign is for, at the moment it starts (spec 4.5)."""
    scope = build_scope(db, campaign.created_by)
    contacts = aud.resolve(db, scope, aud.Audience.model_validate(campaign.audience))
    for item in aud.evaluate(db, contacts, campaign.channel):
        db.add(
            CampaignRecipient(
                campaign_id=campaign.id,
                contact_type=item.contact.type,
                contact_id=item.contact.id,
                name=item.contact.name[:160],
                address=item.address,
                status=RecipientStatus.SKIPPED if item.reason else RecipientStatus.PENDING,
                skip_reason=item.reason,
                processed_at=datetime.now(UTC) if item.reason else None,
            )
        )
    return len(contacts)


def start_now(db: Session, campaign: Campaign, now: datetime) -> None:
    snapshot(db, campaign)
    campaign.status = CampaignStatus.RUNNING
    campaign.started_at = now
    campaign.waiting_reason = None


# -- limits -------------------------------------------------------------------------------


def outside_window(rules: MessagingPolicy, now: datetime) -> str | None:
    local = now.astimezone(tz()).time()
    if rules.window_start <= local < rules.window_end:
        return None
    return (
        f"خارج از ساعت مجاز ارسال ({hhmm(rules.window_start)} تا {hhmm(rules.window_end)});"
        " ارسال در بازه بعدی ادامه می‌یابد."
    )


def sent_today(db: Session, channel: Channel, now: datetime) -> int:
    midnight = datetime.combine(now.astimezone(tz()).date(), time.min, tz())
    return int(
        db.scalar(
            select(func.count())
            .select_from(OutboundMessage)
            .where(
                OutboundMessage.purpose == Purpose.MARKETING,
                OutboundMessage.channel == channel,
                OutboundMessage.created_at >= midnight,
                OutboundMessage.status != MessageStatus.CANCELED,
            )
        )
        or 0
    )


def spent_30_days(db: Session, now: datetime) -> int:
    """Estimated spend of the last 30 days: campaigns and one-off template messages."""
    since = now - timedelta(days=30)
    campaigns = db.scalar(
        select(func.coalesce(func.sum(CampaignRecipient.cost), 0)).where(
            CampaignRecipient.status == RecipientStatus.QUEUED,
            CampaignRecipient.processed_at >= since,
        )
    )
    direct = db.scalar(
        select(func.coalesce(func.sum(DirectMessage.cost), 0)).where(
            DirectMessage.created_at >= since
        )
    )
    return int(campaigns or 0) + int(direct or 0)


# -- sending ----------------------------------------------------------------------------------


def _current_contact(db: Session, recipient: CampaignRecipient) -> aud.Contact | None:
    row: Lead | Customer | None = (
        db.get(Lead, recipient.contact_id)
        if recipient.contact_type == "lead"
        else db.get(Customer, recipient.contact_id)
    )
    if row is None or row.archived_at is not None:
        return None
    return aud.contact_of(row)


def _skip(recipient: CampaignRecipient, reason: str, now: datetime) -> None:
    recipient.status = RecipientStatus.SKIPPED
    recipient.skip_reason = reason
    recipient.processed_at = now


def dispatch(db: Session, campaign: Campaign, rules: MessagingPolicy, now: datetime) -> None:
    """Queues the next batch of one running campaign."""
    reason = outside_window(rules, now)
    limit = rules.sms_daily_limit if campaign.channel is Channel.SMS else rules.email_daily_limit
    room = limit - sent_today(db, campaign.channel, now)
    if reason is None and room <= 0:
        reason = f"سقف روزانه ارسال ({fa(limit)} پیام) پر شده است؛ فردا ادامه می‌یابد."
    if reason is not None:
        if campaign.waiting_reason != reason:
            campaign.waiting_reason = reason
            db.commit()
        return

    batch = list(
        db.scalars(
            select(CampaignRecipient)
            .where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status == RecipientStatus.PENDING,
            )
            .order_by(CampaignRecipient.created_at, CampaignRecipient.id)
            .limit(min(room, BATCH))
            .with_for_update(skip_locked=True, of=CampaignRecipient)
        )
    )
    if not batch:
        finish_if_done(db, campaign, now)
        return

    spent = spent_30_days(db, now)
    contacts = {r.id: _current_contact(db, r) for r in batch}
    addresses = [
        a for a in (aud.address_of(c, campaign.channel) for c in contacts.values() if c) if a
    ]
    blocked = aud.suppressed(db, campaign.channel, addresses)
    already = set(
        db.scalars(
            select(CampaignRecipient.address).where(
                CampaignRecipient.campaign_id == campaign.id,
                CampaignRecipient.status == RecipientStatus.QUEUED,
            )
        )
    )
    for recipient in batch:
        contact = contacts[recipient.id]
        if contact is None:
            _skip(recipient, "پرونده حذف یا بایگانی شده است.", now)
            continue
        # Consent, the do-not-send list and the address are read now, right before sending.
        address, why = aud.check(contact, campaign.channel, blocked)
        if why is None and address in already:
            why = aud.DUPLICATE
        if why is not None or address is None:
            _skip(recipient, why or aud.NO_ADDRESS, now)
            continue
        token = aud.unsubscribe_token(recipient.id)
        body = aud.full_text(campaign.channel, campaign.body, contact.name, token)
        cost = aud.unit_cost(campaign.channel, body, rules)
        if rules.monthly_budget is not None and spent + cost > rules.monthly_budget:
            campaign.status = CampaignStatus.PAUSED
            campaign.waiting_reason = "سقف مصرف ۳۰ روزه پر شده است؛ کمپین متوقف شد."
            notify(
                db,
                campaign.created_by_id,
                NotificationKind.CAMPAIGN,
                f"کمپین «{campaign.name}» به سقف مصرف رسید و متوقف شد",
                f"campaign-budget:{campaign.id}:{now.date().isoformat()}",
                body="ادمین می‌تواند سقف را در تنظیمات کمپین تغییر دهد.",
                link=f"/campaigns/{campaign.id}",
            )
            break
        message = enqueue(
            db,
            campaign.channel,
            Purpose.MARKETING,
            address,
            subject=aud.render(campaign.subject or "", contact.name) or None,
            body=body,
        )
        message.campaign_id = campaign.id
        recipient.address = address
        recipient.status = RecipientStatus.QUEUED
        recipient.message_id = message.id
        recipient.cost = cost
        recipient.processed_at = now
        spent += cost
        already.add(address)
    if campaign.status is CampaignStatus.RUNNING:
        campaign.waiting_reason = None
    db.commit()


def finish_if_done(db: Session, campaign: Campaign, now: datetime) -> None:
    """Running, nobody left to queue: finished once every message has a final status."""
    statuses = list(
        db.scalars(
            select(OutboundMessage.status)
            .join(CampaignRecipient, CampaignRecipient.message_id == OutboundMessage.id)
            .where(CampaignRecipient.campaign_id == campaign.id)
        )
    )
    if any(s not in FINAL_STATUSES for s in statuses):
        campaign.waiting_reason = None
        db.commit()
        return
    ok = any(s in SUCCESS for s in statuses)
    campaign.status = CampaignStatus.COMPLETED if ok or not statuses else CampaignStatus.FAILED
    campaign.finished_at = now
    campaign.waiting_reason = None
    notify(
        db,
        campaign.created_by_id,
        NotificationKind.CAMPAIGN,
        f"کمپین «{campaign.name}» "
        + ("به پایان رسید" if campaign.status is CampaignStatus.COMPLETED else "ناموفق بود"),
        f"campaign-finished:{campaign.id}",
        link=f"/campaigns/{campaign.id}",
    )
    db.commit()


# -- pausing ------------------------------------------------------------------------------


def pause(db: Session, campaign: Campaign) -> int:
    """Stops what has not started: queued messages are canceled and their recipients go
    back to waiting. Returns how many messages were canceled."""
    canceled = list(
        db.scalars(
            update(OutboundMessage)
            .where(
                OutboundMessage.campaign_id == campaign.id,
                OutboundMessage.status == MessageStatus.QUEUED,
            )
            .values(status=MessageStatus.CANCELED, last_error="کمپین متوقف شد.")
            .returning(OutboundMessage.id)
        )
    )
    if canceled:
        db.execute(
            update(CampaignRecipient)
            .where(CampaignRecipient.message_id.in_(canceled))
            .values(status=RecipientStatus.PENDING, message_id=None, cost=0, processed_at=None)
        )
    campaign.status = CampaignStatus.PAUSED
    campaign.waiting_reason = None
    return len(canceled)


# -- unsubscribe ------------------------------------------------------------------------------


def unsubscribe(db: Session, channel: Channel, address: str) -> bool:
    """Adds the address to the do-not-send list and withdraws consent on every lead and
    customer with it. Returns False when it was already there."""
    exists = db.scalar(
        select(Suppression).where(Suppression.channel == channel, Suppression.address == address)
    )
    if exists is None:
        db.add(Suppression(channel=channel, address=address, reason="unsubscribed"))
    now = datetime.now(UTC)
    for model in (Lead, Customer):
        column = model.mobile if channel is Channel.SMS else model.email
        consent = "sms_consent" if channel is Channel.SMS else "email_consent"
        db.execute(
            update(model)
            .where(column == address, getattr(model, consent).is_(True))
            .values({consent: False, "consent_updated_at": now})
        )
    return exists is None


# -- the worker's step ----------------------------------------------------------------------


def tick(db: Session, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    bind = db.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK}):
            return False
        try:
            due = list(
                db.scalars(
                    select(Campaign).where(
                        Campaign.status == CampaignStatus.SCHEDULED, Campaign.scheduled_at <= now
                    )
                )
            )
            for campaign in due:
                start_now(db, campaign, now)
                db.commit()
            rules = policy(db)
            db.commit()
            for campaign_id in list(
                db.scalars(select(Campaign.id).where(Campaign.status == CampaignStatus.RUNNING))
            ):
                running = db.get(Campaign, campaign_id)
                if running is None or running.status is not CampaignStatus.RUNNING:
                    continue
                try:
                    dispatch(db, running, rules, now)
                except Exception:
                    db.rollback()
                    logger.exception("Campaign %s failed to dispatch", campaign_id)
        finally:
            db.rollback()
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK})
            lock.commit()
    return True


def recipient_address(db: Session, recipient_id: uuid.UUID) -> tuple[Channel, str] | None:
    """The channel and address behind an unsubscribe link: a campaign recipient or a
    one-off marketing message."""
    direct = db.get(DirectMessage, recipient_id)
    if direct is not None:
        return direct.channel, direct.address
    row = db.execute(
        select(Campaign.channel, CampaignRecipient.address)
        .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
        .where(CampaignRecipient.id == recipient_id)
    ).first()
    if row is None or row[1] is None:
        return None
    return row[0], row[1]
