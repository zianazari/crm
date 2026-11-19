/** Mirrors the API schemas in apps/api/app/modules/crm/schemas.py. */

export type Ref = { id: string; name: string };
/** A person; ``avatar_version`` is set when they have a profile photo. */
export type UserRef = { id: string; full_name: string; avatar_version?: number | null };
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
  sms_consent: boolean;
  email_consent: boolean;
  consent_updated_at: string | null;
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
  sms_consent: boolean;
  email_consent: boolean;
  consent_updated_at: string | null;
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

// -- sales --------------------------------------------------------------------

export type DealStatus = "open" | "won" | "lost";

export type Stage = { id: string; name: string; sort_order: number; is_active: boolean };

export type DealLimited = {
  access: "limited";
  id: string;
  title: string;
  customer: { id: string; full_name: string };
  stage: Ref;
  status: DealStatus;
  owner: UserRef;
  last_activity_at: string | null;
  created_at: string;
  closed_at: string | null;
};

export type DealFull = Omit<DealLimited, "access"> & {
  access: "full";
  updated_at: string;
  version: number;
  description: string | null;
  organization: Ref | null;
  amount: number | null;
  currency: string;
  expected_close_date: string | null;
  contract_amount: number | null;
  contract_date: string | null;
  lost_reason: string | null;
  archived_at: string | null;
  paid_amount: number;
  outstanding_amount: number | null;
  next_activity: ActivityBrief | null;
};

export type Deal = DealFull | DealLimited;

export type BoardColumn = {
  stage: Stage;
  count: number;
  total_amount: number;
  deals: Deal[];
  truncated: boolean;
};

export type Board = {
  columns: BoardColumn[];
  outcome: {
    closed_from: string;
    won_count: number;
    won_total: number;
    lost_count: number;
    deals: Deal[];
    truncated: boolean;
  };
};

export type DealHistoryEntry = {
  id: string;
  from_stage: Ref | null;
  to_stage: Ref;
  from_status: DealStatus | null;
  to_status: DealStatus;
  changed_by: UserRef;
  reason: string | null;
  changed_at: string;
};

export type Payment = {
  id: string;
  kind: "payment" | "refund";
  amount: number;
  currency: string;
  paid_on: string;
  reference: string | null;
  note: string | null;
  recorded_by: UserRef;
  created_at: string;
  voided_at: string | null;
  void_reason: string | null;
};

export const DEAL_STATUS_LABELS: Record<DealStatus, string> = {
  open: "باز",
  won: "فروش انجام شد",
  lost: "به نتیجه نرسید",
};

// -- activities -----------------------------------------------------------------

export type ActivityType = "call" | "meeting" | "follow_up" | "task";
export type ActivityStatus = "pending" | "in_progress" | "done" | "canceled";
export type Priority = "low" | "normal" | "high";
export type LinkRef = { id: string; name: string };

export type Activity = {
  id: string;
  type: ActivityType;
  title: string;
  description: string | null;
  owner: UserRef;
  created_by: UserRef;
  due_date: string;
  start_at: string | null;
  duration_minutes: number | null;
  priority: Priority;
  reminder_minutes: number | null;
  status: ActivityStatus;
  outcome: string | null;
  cancel_reason: string | null;
  completed_at: string | null;
  completed_by: UserRef | null;
  created_at: string;
  version: number;
  lead: LinkRef | null;
  customer: LinkRef | null;
  deal: LinkRef | null;
  /** Set when the activity came from a team queue. */
  team_task_id: string | null;
  overdue: boolean;
};

export type ActivityBrief = Pick<Activity, "id" | "type" | "title" | "due_date" | "start_at" | "overdue">;

export type Workload = {
  date: string;
  owner: UserRef;
  open_count: number;
  overdue_count: number;
  timed_minutes: number;
  overlaps: { first: string; second: string }[];
};

export type TimelineKind = "activity" | "note" | "stage" | "payment" | "message";

export type TimelineEntry = {
  kind: TimelineKind;
  id: string;
  at: string;
  actor: UserRef;
  title: string;
  body: string | null;
  activity: Activity | null;
  deal: LinkRef | null;
  /** For a sent template message: queued, accepted, delivered, failed… */
  message_status?: string | null;
};

export const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  call: "تماس",
  meeting: "جلسه",
  follow_up: "پیگیری",
  task: "وظیفه",
};

export const PRIORITY_LABELS: Record<Priority, string> = { low: "کم", normal: "عادی", high: "زیاد" };

/** Links an activity or note can carry; names are only for display. */
export type ActivitySubject = { deal?: LinkRef; customer?: LinkRef; lead?: LinkRef };

// -- administration ----------------------------------------------------------------

export type Role = "admin" | "sales_manager" | "sales_rep";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "ادمین",
  sales_manager: "مدیر فروش",
  sales_rep: "کارشناس فروش",
};

export type AdminUser = {
  id: string;
  full_name: string;
  mobile: string | null;
  email: string | null;
  role: Role;
  is_active: boolean;
  team: Ref | null;
  manages_team: Ref | null;
};

export type TeamKind = "sales" | "finance";
export const TEAM_KIND_LABELS: Record<TeamKind, string> = { sales: "فروش", finance: "مالی (عملیاتی)" };

export type Team = {
  id: string;
  name: string;
  kind: TeamKind;
  is_active: boolean;
  manager: UserRef | null;
  member_count: number;
};

export type OpenItems = { leads: number; customers: number; deals: number; activities: number; tickets: number };

export type AuditEntry = {
  id: string;
  action: string;
  actor: UserRef | null;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  at: string;
};
