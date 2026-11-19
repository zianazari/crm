/** Booking: staff settings and links, the customer's link page (/api/book/<token>) and
 * the portal's own bookings. */

import { ApiError } from "@/lib/api";
import type { UserRef } from "@/lib/types";

export type Channel = "sms" | "email";

export type Rule = { weekday: number; start: string; end: string };

export type MeetingType = {
  id: string;
  title: string;
  duration_minutes: number;
  description: string | null;
  is_active: boolean;
};

export type DayOff = { id: string; start_date: string; end_date: string; reason: string; organization: boolean };

export type BookingSettings = {
  user: UserRef;
  timezone: string;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  min_notice_minutes: number;
  horizon_days: number;
  change_deadline_hours: number;
  rules: Rule[];
  meeting_types: MeetingType[];
  exceptions: DayOff[];
};

export type Slots = { timezone: string; duration_minutes: number; days: { date: string; slots: string[] }[] };

export type BookingStatus = "confirmed" | "canceled" | "rescheduled";

export type StaffBooking = {
  id: string;
  status: BookingStatus;
  start_at: string;
  end_at: string;
  meeting_title: string;
  user: UserRef;
  customer: { id: string; full_name: string };
  activity_id: string;
  deal_id: string | null;
  contact_channel: Channel;
  created_at: string;
  canceled_at: string | null;
  cancel_reason: string | null;
  canceled_by: UserRef | null;
  rescheduled_to_id: string | null;
};

export type LinkState = "open" | "booked" | "expired" | "revoked";

export type BookingLink = {
  id: string;
  user: UserRef;
  customer: { id: string; full_name: string };
  meeting_type: MeetingType;
  deal_id: string | null;
  created_by: UserRef;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  sent_via: Channel | null;
  state: LinkState;
  booking: StaffBooking | null;
};

export const LINK_STATE_LABELS: Record<LinkState, string> = {
  open: "منتظر انتخاب زمان",
  booked: "رزرو شد",
  expired: "منقضی",
  revoked: "باطل‌شده",
};

// -- the customer side ------------------------------------------------------------------

export type LinkView = {
  state: LinkState;
  staff_name: string;
  meeting: MeetingType;
  timezone: string;
  expires_at: string;
  change_deadline_hours: number;
  verified: boolean;
  booking: { id: string; start_at: string; end_at: string; can_change: boolean; change_until: string } | null;
};

export type PortalBooking = {
  id: string;
  status: BookingStatus;
  meeting_title: string;
  meeting_description: string | null;
  staff_name: string;
  start_at: string;
  end_at: string;
  can_change: boolean;
  change_until: string;
  canceled_at: string | null;
};

function cookie(name: string): string {
  return (
    document.cookie
      .split("; ")
      .find((part) => part.startsWith(`${name}=`))
      ?.slice(name.length + 1) ?? ""
  );
}

/** For the public booking page: no redirects, the CSRF header from whichever verification
 * (the link's own, or a portal session) the customer has. */
export async function bookFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (method !== "GET") headers.set("X-CSRF-Token", cookie("crm_booking_csrf") || cookie("crm_portal_csrf"));
  let res: Response;
  try {
    res = await fetch(`/api/book${path}`, { ...init, method, headers });
  } catch {
    throw new ApiError(0, "ارتباط با سرور برقرار نشد.");
  }
  if (!res.ok) {
    let message = "خطایی رخ داد. دوباره تلاش کنید.";
    try {
      const detail = ((await res.json()) as { detail?: unknown }).detail;
      if (typeof detail === "string") message = detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}
