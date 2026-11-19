/** Campaigns (spec 4.5): API shapes and labels. */

import type { LeadStatus, Page, UserRef } from "@/lib/types";

export type Channel = "sms" | "email";
export type CampaignStatus = "draft" | "scheduled" | "running" | "paused" | "completed" | "failed";

export type ContactRef = { type: "lead" | "customer"; id: string; name?: string | null };
export type SegmentFilters = {
  contact_types: ("lead" | "customer")[];
  source_ids: string[];
  tag_ids: string[];
  lead_statuses: LeadStatus[];
  owner_ids: string[];
  created_from: string | null;
  created_to: string | null;
};
export type Audience = { kind: "selected" | "segment"; contacts: ContactRef[]; filters: SegmentFilters };

export type Stats = {
  total: number;
  pending: number;
  skipped: number;
  in_queue: number;
  accepted: number;
  delivered: number;
  failed: number;
  unknown: number;
  cost: number;
};

export type Campaign = {
  id: string;
  name: string;
  channel: Channel;
  subject: string | null;
  body: string;
  audience: Audience;
  status: CampaignStatus;
  scheduled_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  waiting_reason: string | null;
  created_by: UserRef;
  created_at: string;
  updated_at: string;
  version: number;
  stats: Stats;
};

export type Preview = {
  contacts: number;
  eligible: number;
  excluded: Record<string, number>;
  parts: number | null;
  unit_cost: number;
  estimated_cost: number;
  sample_name: string | null;
  sample_subject: string | null;
  sample_text: string | null;
  daily_limit: number;
  window: string;
  budget_left: number | null;
};

export type RecipientStatus = "pending" | "skipped" | "in_queue" | "accepted" | "delivered" | "failed" | "unknown";

export type Recipient = {
  id: string;
  contact_type: "lead" | "customer";
  contact_id: string;
  name: string;
  address: string | null;
  status: RecipientStatus;
  reason: string | null;
  sent_at: string | null;
  delivered_at: string | null;
};

export type Policy = {
  window_start: string;
  window_end: string;
  sms_daily_limit: number;
  email_daily_limit: number;
  sms_unit_price: number;
  email_unit_price: number;
  monthly_budget: number | null;
  user_daily_limit: number;
  spent_30_days: number;
};

export type Suppression = {
  id: string;
  channel: Channel;
  address: string;
  reason: "unsubscribed" | "manual";
  note: string | null;
  created_at: string;
};

export type CampaignPage = Page<Campaign>;

export const CHANNEL_LABELS: Record<Channel, string> = { sms: "پیامک", email: "ایمیل" };

export const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, string> = {
  draft: "پیش‌نویس",
  scheduled: "زمان‌بندی‌شده",
  running: "در حال اجرا",
  paused: "متوقف‌شده",
  completed: "تکمیل‌شده",
  failed: "ناموفق",
};

export const RECIPIENT_STATUS_LABELS: Record<RecipientStatus, string> = {
  pending: "در انتظار ارسال",
  skipped: "ارسال نشد",
  in_queue: "در صف",
  accepted: "پذیرفته‌شده توسط سرویس‌دهنده",
  delivered: "تحویل‌شده",
  failed: "ناموفق",
  unknown: "نامشخص",
};

export const EMPTY_FILTERS: SegmentFilters = {
  contact_types: ["lead", "customer"],
  source_ids: [],
  tag_ids: [],
  lead_statuses: [],
  owner_ids: [],
  created_from: null,
  created_to: null,
};

/** "YYYY-MM-DD" + "HH:MM" in Tehran as an ISO instant (Iran has no daylight saving). */
export function tehranInstant(date: string, time: string): string {
  return `${date}T${time}:00+03:30`;
}
