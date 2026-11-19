"""Who a campaign reaches (spec 4.5): chosen contacts or a filtered segment of leads and
customers, always within the campaign author's scope, and why anyone is left out.

The same checks run three times: for the preview before starting, when the recipient
list is fixed, and again right before each message is queued.
"""

import hashlib
import hmac
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.normalize import normalize_email, normalize_mobile
from app.modules.campaigns.models import Suppression
from app.modules.crm.access import AccessScope
from app.modules.crm.models import Customer, Lead, LeadStatus, customer_tags, lead_tags
from app.modules.messaging.models import Channel

ContactType = Literal["lead", "customer"]

MAX_SELECTED = 5000


class ContactRef(BaseModel):
    type: ContactType
    id: uuid.UUID
    # Display only, so the chosen list reads well when the draft is reopened; the
    # recipient's name always comes from the record itself.
    name: str | None = Field(default=None, max_length=160)


BOTH: tuple[ContactType, ...] = ("lead", "customer")


class SegmentFilters(BaseModel):
    contact_types: list[ContactType] = Field(default_factory=lambda: list(BOTH))
    source_ids: list[uuid.UUID] = []
    tag_ids: list[uuid.UUID] = []
    lead_statuses: list[LeadStatus] = []
    owner_ids: list[uuid.UUID] = []
    created_from: date | None = None
    created_to: date | None = None


class Audience(BaseModel):
    kind: Literal["selected", "segment"] = "selected"
    contacts: list[ContactRef] = Field(default=[], max_length=MAX_SELECTED)
    filters: SegmentFilters = Field(default_factory=SegmentFilters)


@dataclass
class Contact:
    type: ContactType
    id: uuid.UUID
    name: str
    mobile: str | None
    email: str | None
    sms_consent: bool
    email_consent: bool
    created_at: datetime


def _contact(row: Lead | Customer) -> Contact:
    return Contact(
        type="lead" if isinstance(row, Lead) else "customer",
        id=row.id,
        name=row.full_name,
        mobile=row.mobile,
        email=row.email,
        sms_consent=row.sms_consent,
        email_consent=row.email_consent,
        created_at=row.created_at,
    )


def _bounds(filters: SegmentFilters) -> tuple[datetime | None, datetime | None]:
    tz = ZoneInfo(get_settings().timezone)
    start = datetime.combine(filters.created_from, time.min, tz) if filters.created_from else None
    end = datetime.combine(filters.created_to, time.max, tz) if filters.created_to else None
    return start, end


def resolve(db: Session, scope: AccessScope, audience: Audience) -> list[Contact]:
    """Contacts the author fully sees that match the audience; archived records and
    converted leads (their customer is the contact) never count."""
    leads = select(Lead).where(
        Lead.archived_at.is_(None),
        Lead.status != LeadStatus.CONVERTED,
        scope.full_access_filter(Lead.owner_id),
    )
    customers = select(Customer).where(
        Customer.archived_at.is_(None), scope.full_access_filter(Customer.owner_id)
    )
    want_leads = want_customers = True
    if audience.kind == "selected":
        lead_ids = [c.id for c in audience.contacts if c.type == "lead"]
        customer_ids = [c.id for c in audience.contacts if c.type == "customer"]
        leads = leads.where(Lead.id.in_(lead_ids))
        customers = customers.where(Customer.id.in_(customer_ids))
        want_leads, want_customers = bool(lead_ids), bool(customer_ids)
    else:
        f = audience.filters
        want_leads, want_customers = "lead" in f.contact_types, "customer" in f.contact_types
        start, end = _bounds(f)
        if f.source_ids:
            leads = leads.where(Lead.source_id.in_(f.source_ids))
            customers = customers.where(Customer.source_id.in_(f.source_ids))
        if f.tag_ids:
            leads = leads.where(
                Lead.id.in_(select(lead_tags.c.lead_id).where(lead_tags.c.tag_id.in_(f.tag_ids)))
            )
            customers = customers.where(
                Customer.id.in_(
                    select(customer_tags.c.customer_id).where(customer_tags.c.tag_id.in_(f.tag_ids))
                )
            )
        if f.lead_statuses:
            leads = leads.where(Lead.status.in_(f.lead_statuses))
        if f.owner_ids:
            leads = leads.where(Lead.owner_id.in_(f.owner_ids))
            customers = customers.where(Customer.owner_id.in_(f.owner_ids))
        if start:
            leads = leads.where(Lead.created_at >= start)
            customers = customers.where(Customer.created_at >= start)
        if end:
            leads = leads.where(Lead.created_at <= end)
            customers = customers.where(Customer.created_at <= end)
    result: list[Contact] = []
    # Customers first: when a customer and a lead share an address, the customer stays.
    if want_customers:
        result += [_contact(c) for c in db.scalars(customers.order_by(Customer.created_at))]
    if want_leads:
        result += [_contact(lead) for lead in db.scalars(leads.order_by(Lead.created_at))]
    return result


# -- eligibility ---------------------------------------------------------------------------

NO_ADDRESS = "نشانی این کانال ثبت نشده است."
BAD_ADDRESS = "نشانی معتبر نیست."
NO_CONSENT = "اجازه دریافت پیام تبلیغاتی نداده است."
SUPPRESSED = "در فهرست عدم ارسال است."
DUPLICATE = "تکراری: همین نشانی برای مخاطب دیگری در این کمپین است."


def address_of(contact: Contact, channel: Channel) -> str | None:
    raw = contact.mobile if channel is Channel.SMS else contact.email
    if not raw:
        return None
    return normalize_mobile(raw) if channel is Channel.SMS else normalize_email(raw)


def suppressed(db: Session, channel: Channel, addresses: list[str]) -> set[str]:
    if not addresses:
        return set()
    return set(
        db.scalars(
            select(Suppression.address).where(
                Suppression.channel == channel, Suppression.address.in_(addresses)
            )
        )
    )


def check(contact: Contact, channel: Channel, blocked: set[str]) -> tuple[str | None, str | None]:
    """(address, reason the contact cannot receive marketing, or None)."""
    raw = contact.mobile if channel is Channel.SMS else contact.email
    if not raw:
        return None, NO_ADDRESS
    address = address_of(contact, channel)
    if address is None:
        return None, BAD_ADDRESS
    consent = contact.sms_consent if channel is Channel.SMS else contact.email_consent
    if not consent:
        return address, NO_CONSENT
    if address in blocked:
        return address, SUPPRESSED
    return address, None


@dataclass
class Evaluated:
    contact: Contact
    address: str | None
    reason: str | None  # None = will be sent


def evaluate(db: Session, contacts: list[Contact], channel: Channel) -> list[Evaluated]:
    """Every contact with its address and, if it will not be sent, the reason.
    Of several eligible contacts with the same address, only the first is sent."""
    addresses = [a for a in (address_of(c, channel) for c in contacts) if a]
    blocked = suppressed(db, channel, addresses)
    seen: set[str] = set()
    result = []
    for contact in contacts:
        address, reason = check(contact, channel, blocked)
        if reason is None and address is not None:
            if address in seen:
                reason = DUPLICATE
            seen.add(address)
        result.append(Evaluated(contact, address, reason))
    return result


# -- message text ---------------------------------------------------------------------------

_GSM = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


def sms_parts(text: str) -> int:
    """SMS parts a text needs: 160/153 characters in GSM-7, 70/67 otherwise (Persian)."""
    gsm = all(ch in _GSM for ch in text)
    single, multi = (160, 153) if gsm else (70, 67)
    length = len(text)
    return 1 if length <= single else math.ceil(length / multi)


def render(template: str, name: str) -> str:
    return template.replace("{name}", name).strip()


def unsubscribe_token(recipient_id: uuid.UUID) -> str:
    secret = get_settings().jwt_secret.get_secret_value().encode()
    mac = hmac.new(secret, b"unsubscribe:" + recipient_id.bytes, hashlib.sha256).hexdigest()
    return recipient_id.hex + mac[:16]


def read_token(token: str) -> uuid.UUID | None:
    if len(token) != 48:
        return None
    try:
        recipient_id = uuid.UUID(hex=token[:32])
    except ValueError:
        return None
    return recipient_id if hmac.compare_digest(unsubscribe_token(recipient_id), token) else None


def footer(channel: Channel, token: str) -> str:
    url = f"{get_settings().public_web_url.rstrip('/')}/u/{token}"
    if channel is Channel.SMS:
        return f"\nلغو: {url}"
    return f"\n\n—\nبرای لغو دریافت این پیام‌ها: {url}"


def full_text(channel: Channel, body: str, name: str, token: str) -> str:
    return render(body, name) + footer(channel, token)


def unit_cost(channel: Channel, text: str, policy: Any) -> int:
    if channel is Channel.SMS:
        return int(sms_parts(text) * policy.sms_unit_price)
    return int(policy.email_unit_price)
