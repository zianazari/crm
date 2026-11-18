/** Automation rules (spec 4.6): API shapes and the block catalog shared by the builder. */

import {
  Bell,
  CalendarPlus,
  Filter,
  Hourglass,
  Mail,
  MessageSquareText,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { UserRef } from "@/lib/types";

export type RuleStatus = "draft" | "active" | "paused";
export type RepeatPolicy = "every_time" | "once_per_record";
export type ExecutionStatus = "running" | "waiting" | "completed" | "skipped" | "failed" | "canceled";

export type BlockKind =
  | "trigger"
  | "condition"
  | "create_activity"
  | "notify"
  | "send_sms"
  | "send_email"
  | "delay";

export type BlockConfig = Record<string, unknown>;

export type GraphNode = {
  id: string;
  kind: BlockKind;
  config: BlockConfig;
  position: { x: number; y: number };
};
export type GraphEdge = { id: string; source: string; target: string };
export type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type Problem = { node_id: string | null; message: string };

export type RuleVersion = { id: string; number: number; published_by: UserRef; published_at: string };

export type RuleSummary = {
  id: string;
  name: string;
  description: string | null;
  status: RuleStatus;
  trigger_event: string | null;
  active_version: RuleVersion | null;
  created_by: UserRef;
  updated_at: string;
  runs_last_30_days: number;
  failures_last_30_days: number;
};

export type RuleDetail = RuleSummary & {
  repeat_policy: RepeatPolicy;
  max_runs_per_hour: number;
  draft: Graph;
  draft_updated_at: string | null;
  active_since: string | null;
  unpublished_changes: boolean;
  problems: Problem[];
};

export type Template = { key: string; name: string; description: string };

export type TestStep = {
  node_id: string;
  kind: BlockKind;
  outcome: "passed" | "not_met" | "would_run" | "would_skip" | "wait" | "stopped";
  detail: string;
};
export type TestResult = { problems: Problem[]; subject: string | null; steps: TestStep[] };

export type ExecutionLogEntry = {
  step: number;
  type: string;
  result: string;
  detail?: string;
  at: string;
  [key: string]: unknown;
};

export type Execution = {
  id: string;
  status: ExecutionStatus;
  subject_type: SubjectType;
  subject_id: string;
  subject_name: string | null;
  version_number: number;
  log: ExecutionLogEntry[];
  error: string | null;
  created_at: string;
  finished_at: string | null;
  resume_at: string | null;
};

export type SubjectType = "lead" | "customer" | "deal" | "activity";

// -- labels ------------------------------------------------------------------------

export const RULE_STATUS_LABELS: Record<RuleStatus, string> = {
  draft: "پیش‌نویس",
  active: "فعال",
  paused: "متوقف",
};

export const EXECUTION_STATUS_LABELS: Record<ExecutionStatus, string> = {
  running: "در حال اجرا",
  waiting: "در انتظار تأخیر",
  completed: "انجام شد",
  skipped: "رد شد",
  failed: "ناموفق",
  canceled: "لغو شد",
};

export const EVENT_LABELS: Record<string, string> = {
  "lead.created": "ثبت مشتری احتمالی",
  "record.assigned": "انتساب مسئول",
  "deal.stage_entered": "ورود فروش به مرحله",
  "deal.won": "فروش انجام شد",
  "deal.lost": "فروش به نتیجه نرسید",
  "activity.due": "رسیدن موعد فعالیت",
  "deal.inactive": "بی‌فعالیتی فروش",
};

export const SUBJECT_LABELS: Record<SubjectType, string> = {
  lead: "مشتری احتمالی",
  customer: "مشتری",
  deal: "فروش",
  activity: "فعالیت",
};

export const CONDITION_FIELD_LABELS: Record<string, string> = {
  stage: "مرحله فروش",
  deal_status: "وضعیت فروش",
  lead_status: "وضعیت مشتری احتمالی",
  source: "منبع جذب",
  tag: "برچسب",
  owner: "مسئول",
};

export const DELAY_UNIT_LABELS: Record<string, string> = { minutes: "دقیقه", hours: "ساعت", days: "روز" };

export function subjectOf(trigger: BlockConfig | undefined): SubjectType | null {
  const event = trigger?.event;
  if (event === "record.assigned") {
    const entity = trigger?.entity_type;
    return entity === "lead" || entity === "customer" || entity === "deal" ? entity : null;
  }
  if (event === "lead.created") return "lead";
  if (event === "activity.due") return "activity";
  if (typeof event === "string" && event.startsWith("deal.")) return "deal";
  return null;
}

/** Condition fields that make sense for the records a trigger produces (mirrors the API). */
export function fieldsFor(subject: SubjectType | null): string[] {
  const common = ["source", "tag", "owner"];
  if (subject === "deal") return ["stage", "deal_status", ...common];
  if (subject === "lead") return ["lead_status", ...common];
  if (subject === "activity") return ["stage", "deal_status", "lead_status", ...common];
  return common;
}

// -- block catalog -------------------------------------------------------------------

export type BlockDef = {
  kind: BlockKind;
  label: string;
  hint: string;
  icon: LucideIcon;
  /** Tailwind classes for the block's accent (icon chip and palette item). */
  tone: string;
  defaults: () => BlockConfig;
};

export const BLOCKS: BlockDef[] = [
  {
    kind: "trigger",
    label: "رویداد",
    hint: "شروع اتوماسیون",
    icon: Zap,
    tone: "bg-amber-100 text-amber-800",
    defaults: () => ({ event: "lead.created" }),
  },
  {
    kind: "condition",
    label: "شرط",
    hint: "فقط اگر برقرار باشد ادامه می‌دهد",
    icon: Filter,
    tone: "bg-sky-100 text-sky-800",
    defaults: () => ({ field: "", operator: "in", values: [] }),
  },
  {
    kind: "create_activity",
    label: "فعالیت",
    hint: "ساخت تماس، جلسه یا پیگیری",
    icon: CalendarPlus,
    tone: "bg-emerald-100 text-emerald-800",
    defaults: () => ({
      activity_type: "follow_up",
      title: "پیگیری {name}",
      due_in_days: 0,
      assignee: "record_owner",
    }),
  },
  {
    kind: "notify",
    label: "اعلان داخلی",
    hint: "اعلان به کارشناس یا مدیر",
    icon: Bell,
    tone: "bg-violet-100 text-violet-800",
    defaults: () => ({ recipient: "record_owner", title: "" }),
  },
  {
    kind: "send_sms",
    label: "پیامک",
    hint: "فقط با اجازه مخاطب",
    icon: MessageSquareText,
    tone: "bg-rose-100 text-rose-800",
    defaults: () => ({ text: "" }),
  },
  {
    kind: "send_email",
    label: "ایمیل",
    hint: "فقط با اجازه مخاطب",
    icon: Mail,
    tone: "bg-indigo-100 text-indigo-800",
    defaults: () => ({ subject: "", text: "" }),
  },
  {
    kind: "delay",
    label: "تأخیر",
    hint: "صبر پیش از قدم بعد",
    icon: Hourglass,
    tone: "bg-stone-200 text-stone-800",
    defaults: () => ({ amount: 1, unit: "days" }),
  },
];

export const BLOCK_BY_KIND = Object.fromEntries(BLOCKS.map((b) => [b.kind, b])) as Record<BlockKind, BlockDef>;

export const PLACEHOLDER_HINT = "می‌توانید از {name} (نام مخاطب)، {deal} (عنوان فروش) و {owner} (مسئول) استفاده کنید.";

// -- graph helpers -------------------------------------------------------------------

export function newNodeId(nodes: GraphNode[]): string {
  let n = nodes.length + 1;
  const ids = new Set(nodes.map((node) => node.id));
  while (ids.has(`n${n}`)) n += 1;
  return `n${n}`;
}

/** The blocks reachable from the trigger, in execution order (edges only, never positions). */
export function pathOrder(graph: Graph): string[] {
  const trigger = graph.nodes.find((n) => n.kind === "trigger");
  if (!trigger) return [];
  const next = new Map(graph.edges.map((e) => [e.source, e.target]));
  const order = [trigger.id];
  const seen = new Set(order);
  let current = next.get(trigger.id);
  while (current && !seen.has(current)) {
    order.push(current);
    seen.add(current);
    current = next.get(current);
  }
  return order;
}

/** Why a new connection would be refused, or null when it is allowed (the API re-checks). */
export function connectionProblem(graph: Graph, source: string, target: string): string | null {
  if (source === target) return "بلوک به خودش وصل نمی‌شود.";
  const targetNode = graph.nodes.find((n) => n.id === target);
  if (targetNode?.kind === "trigger") return "به رویداد شروع نمی‌توان وصل شد.";
  if (graph.edges.some((e) => e.source === source)) return "هر بلوک فقط یک بلوک بعدی دارد؛ ابتدا اتصال قبلی را حذف کنید.";
  if (graph.edges.some((e) => e.target === target)) return "این بلوک ورودی دارد؛ مسیر باید خطی باشد.";
  // Following the path from the target must not lead back to the source.
  const next = new Map(graph.edges.map((e) => [e.source, e.target]));
  let current: string | undefined = target;
  const seen = new Set<string>();
  while (current && !seen.has(current)) {
    if (current === source) return "این اتصال حلقه می‌سازد.";
    seen.add(current);
    current = next.get(current);
  }
  return null;
}
