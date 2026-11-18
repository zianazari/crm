"use client";

import { Badge } from "@/components/ui/badge";
import {
  CONDITION_FIELD_LABELS,
  DELAY_UNIT_LABELS,
  EVENT_LABELS,
  EXECUTION_STATUS_LABELS,
  RULE_STATUS_LABELS,
  SUBJECT_LABELS,
  type BlockConfig,
  type BlockKind,
  type ExecutionStatus,
  type RuleStatus,
  type SubjectType,
} from "@/lib/automation";
import { formatNumber } from "@/lib/format";
import { useAssignableUsers, useSources, useStages, useTags } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS, DEAL_STATUS_LABELS, LEAD_STATUS_LABELS, type ActivityType } from "@/lib/types";
import { cn } from "@/lib/utils";

const RULE_STYLES: Record<RuleStatus, string> = {
  draft: "bg-secondary text-secondary-foreground",
  active: "bg-success text-success-foreground",
  paused: "bg-amber-100 text-amber-900",
};

export function RuleStatusBadge({ status }: { status: RuleStatus }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", RULE_STYLES[status])}>
      {RULE_STATUS_LABELS[status]}
    </Badge>
  );
}

const EXECUTION_STYLES: Record<ExecutionStatus, string> = {
  running: "bg-sky-50 text-sky-800",
  waiting: "bg-amber-100 text-amber-900",
  completed: "bg-success text-success-foreground",
  skipped: "bg-secondary text-secondary-foreground",
  failed: "bg-destructive/10 text-destructive",
  canceled: "bg-muted text-muted-foreground",
};

export function ExecutionStatusBadge({ status }: { status: ExecutionStatus }) {
  return (
    <Badge variant="secondary" className={cn("font-medium", EXECUTION_STYLES[status])}>
      {EXECUTION_STATUS_LABELS[status]}
    </Badge>
  );
}

/** Choices for a condition's values, by field (names resolved from settings). */
export function useConditionOptions(field: string): { value: string; label: string }[] {
  const { data: stages = [] } = useStages();
  const { data: sources = [] } = useSources();
  const { data: tags = [] } = useTags();
  const { data: users = [] } = useAssignableUsers();
  switch (field) {
    case "stage":
      return stages.map((s) => ({ value: s.id, label: s.name }));
    case "source":
      return sources.map((s) => ({ value: s.id, label: s.name }));
    case "tag":
      return tags.map((t) => ({ value: t.id, label: t.name }));
    case "owner":
      return users.map((u) => ({ value: u.id, label: u.full_name }));
    case "deal_status":
      return Object.entries(DEAL_STATUS_LABELS).map(([value, label]) => ({ value, label }));
    case "lead_status":
      return Object.entries(LEAD_STATUS_LABELS).map(([value, label]) => ({ value, label }));
    default:
      return [];
  }
}

export function useUserName() {
  const { data: users = [] } = useAssignableUsers();
  return (id: unknown) => users.find((u) => u.id === id)?.full_name ?? "کاربر انتخاب‌نشده";
}

const RECIPIENTS: Record<string, string> = {
  record_owner: "مسئول پرونده",
  owner_manager: "مدیر تیم مسئول",
  user: "کاربر مشخص",
};

/** Placeholders read as words on the canvas (raw braces scramble right-to-left text). */
function readable(text: string): string {
  return text.replaceAll("{name}", "‹نام مخاطب›").replaceAll("{deal}", "‹عنوان فروش›").replaceAll("{owner}", "‹مسئول›");
}

/** One line describing what a block will do, shown on the canvas. */
export function BlockSummary({ kind, config }: { kind: BlockKind; config: BlockConfig }) {
  const options = useConditionOptions(kind === "condition" ? String(config.field ?? "") : "");
  const userName = useUserName();
  let text = "";
  switch (kind) {
    case "trigger": {
      const event = String(config.event ?? "");
      text = EVENT_LABELS[event] ?? "رویداد انتخاب نشده";
      if (event === "record.assigned" && config.entity_type) {
        text += ` (${SUBJECT_LABELS[config.entity_type as SubjectType] ?? ""})`;
      }
      if (event === "deal.inactive") text += ` برای ${formatNumber(Number(config.days ?? 0))} روز`;
      break;
    }
    case "condition": {
      const field = String(config.field ?? "");
      if (!field) {
        text = "ویژگی شرط انتخاب نشده";
        break;
      }
      const values = (Array.isArray(config.values) ? config.values : []).map(
        (v) => options.find((o) => o.value === v)?.label ?? "؟",
      );
      const op = config.operator === "not_in" ? "نباشد" : "باشد";
      text = `${CONDITION_FIELD_LABELS[field]} ${values.length ? `«${values.join("، ")}»` : "…"} ${op}`;
      break;
    }
    case "create_activity": {
      const type = ACTIVITY_TYPE_LABELS[config.activity_type as ActivityType] ?? "فعالیت";
      const who = config.assignee === "user" ? userName(config.user_id) : "مسئول پرونده";
      const due = Number(config.due_in_days ?? 0);
      text = `${type} «${String(config.title ?? "")}» برای ${who}، ${due ? `${formatNumber(due)} روز بعد` : "همان روز"}`;
      break;
    }
    case "notify": {
      const who = config.recipient === "user" ? userName(config.user_id) : RECIPIENTS[String(config.recipient)] ?? "";
      text = `به ${who}: ${String(config.title ?? "") || "…"}`;
      break;
    }
    case "send_sms":
      text = String(config.text ?? "") || "متن پیامک نوشته نشده";
      break;
    case "send_email":
      text = String(config.subject ?? "") || "موضوع ایمیل نوشته نشده";
      break;
    case "delay":
      text = `${formatNumber(Number(config.amount ?? 0))} ${DELAY_UNIT_LABELS[String(config.unit)] ?? ""} صبر`;
      break;
  }
  return <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">{readable(text)}</p>;
}

export { RECIPIENTS };
