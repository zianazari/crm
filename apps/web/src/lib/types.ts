/** Mirrors the API schemas in apps/api/app/modules/crm/schemas.py. */

export type Ref = { id: string; name: string };
export type UserRef = { id: string; full_name: string };
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type LeadStatus = "new" | "working" | "qualified" | "disqualified" | "converted";
export type ContactChannel = "phone" | "sms" | "email";

export type LeadLimited = {
  access: "limited";
  id: string;
  full_name: string;
  status: LeadStatus;
  owner: UserRef;
  last_contacted_at: string | null;
  created_at: string;
};

export type LeadFull = Omit<LeadLimited, "access"> & {
  access: "full";
  updated_at: string;
  mobile: string | null;
  email: string | null;
  company_name: string | null;
  description: string | null;
  source: Ref | null;
  acquisition: Record<string, unknown> | null;
  tags: Ref[];
  disqualify_reason: string | null;
  converted_customer_id: string | null;
  converted_at: string | null;
  archived_at: string | null;
};

export type Lead = LeadFull | LeadLimited;

export type CustomerLimited = {
  access: "limited";
  id: string;
  full_name: string;
  owner: UserRef;
  last_activity_at: string | null;
  created_at: string;
};

export type CustomerFull = Omit<CustomerLimited, "access"> & {
  access: "full";
  updated_at: string;
  mobile: string | null;
  phone: string | null;
  email: string | null;
  preferred_channel: ContactChannel | null;
  description: string | null;
  source: Ref | null;
  tags: Ref[];
  organizations: { organization: Ref; job_title: string | null }[];
  archived_at: string | null;
};

export type Customer = CustomerFull | CustomerLimited;

export type Organization = {
  id: string;
  name: string;
  phone: string | null;
  website: string | null;
  created_at: string;
};

export type LeadSource = { id: string; name: string; is_active: boolean; sort_order: number };

export type DuplicateMatch = {
  kind: "customer" | "lead";
  id: string;
  full_name: string;
  owner: UserRef;
  matched_on: ("mobile" | "email")[];
  access: "full" | "limited";
};

export type ConvertResult = {
  lead_id: string;
  customer_id: string;
  created_customer: boolean;
  organization_id: string | null;
};

export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  new: "جدید",
  working: "در حال پیگیری",
  qualified: "واجد شرایط",
  disqualified: "نامناسب",
  converted: "تبدیل‌شده",
};

export const CHANNEL_LABELS: Record<ContactChannel, string> = {
  phone: "تماس تلفنی",
  sms: "پیامک",
  email: "ایمیل",
};
