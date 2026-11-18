"use client";

import Link from "next/link";
import { useState } from "react";
import {
  AlarmClock,
  CalendarClock,
  CircleCheck,
  ClipboardList,
  EllipsisVertical,
  Loader2,
  Phone,
  RefreshCw,
  TriangleAlert,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";
import { Field, Owner } from "@/components/crm/bits";
import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { ReasonDialog } from "@/components/crm/reason-dialog";
import { TaskContextButton } from "@/components/crm/team-task-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { addDays, dayLabel, formatTime, todayIso } from "@/lib/jalali";
import { keys, useMe } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS, type Activity, type ActivityBrief, type ActivityType } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPE_ICONS: Record<ActivityType, LucideIcon> = {
  call: Phone,
  meeting: Users,
  follow_up: RefreshCw,
  task: ClipboardList,
};

export function ActivityTypeIcon({ type, className }: { type: ActivityType; className?: string }) {
  const Icon = TYPE_ICONS[type];
  return <Icon className={className} aria-label={ACTIVITY_TYPE_LABELS[type]} />;
}

/** «فردا، ۱۰:۳۰» or «امروز (بدون ساعت)». */
export function whenLabel(a: Pick<Activity, "due_date" | "start_at">): string {
  const day = dayLabel(a.due_date, todayIso());
  return a.start_at ? `${day}، ${formatTime(a.start_at)}` : day;
}

/** The next-action line on a board card: overdue and missing follow-up are spelled out,
 * not shown by colour alone (spec 4.3). */
export function NextActionPill({ next }: { next: ActivityBrief | null }) {
  if (!next) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
        <TriangleAlert className="size-3.5" aria-hidden />
        بدون پیگیری
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        next.overdue ? "bg-warning text-warning-foreground" : "bg-success text-success-foreground",
      )}
    >
      {next.overdue ? <AlarmClock className="size-3.5 shrink-0" aria-hidden /> : <ActivityTypeIcon type={next.type} className="size-3.5 shrink-0" />}
      <span className="truncate">
        {next.overdue ? "عقب‌افتاده: " : ""}
        {ACTIVITY_TYPE_LABELS[next.type]} {whenLabel(next)}
      </span>
    </span>
  );
}

export function ActivityItem({ activity, showLinks = true }: { activity: Activity; showLinks?: boolean }) {
  const queryClient = useQueryClient();
  const [completing, setCompleting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const open = activity.status === "pending" || activity.status === "in_progress";

  async function cancel(reason: string) {
    try {
      await apiFetch(`/activities/${activity.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason, version: activity.version }),
      });
      await invalidateAll(queryClient);
      toast.success("فعالیت لغو شد.");
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
      return false;
    }
  }

  return (
    <div className="flex items-start gap-3 rounded-lg border bg-card p-3 text-sm">
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg",
          activity.overdue ? "bg-warning text-warning-foreground" : "bg-accent text-accent-foreground",
        )}
      >
        <ActivityTypeIcon type={activity.type} className="size-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className={cn("font-medium", activity.status === "canceled" && "line-through")}>{activity.title}</p>
          {activity.overdue ? (
            <Badge variant="secondary" className="bg-warning text-warning-foreground">
              <AlarmClock aria-hidden />
              عقب‌افتاده
            </Badge>
          ) : null}
          {activity.priority === "high" ? <Badge variant="outline">اولویت زیاد</Badge> : null}
        </div>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <CalendarClock className="size-3.5" aria-hidden />
            {whenLabel(activity)}
            {activity.duration_minutes ? ` · ${formatNumber(activity.duration_minutes)} دقیقه` : ""}
          </span>
          <Owner user={activity.owner} />
          {showLinks ? <Links activity={activity} /> : null}
        </p>
        {activity.team_task_id ? <TaskContextButton taskId={activity.team_task_id} /> : null}
        {activity.description ? <p className="text-muted-foreground">{activity.description}</p> : null}
      </div>
      {open ? (
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="outline" onClick={() => setCompleting(true)}>
            <CircleCheck aria-hidden />
            انجام شد
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger aria-label="عملیات بیشتر" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted">
              <EllipsisVertical className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => setEditing(true)}>ویرایش یا تغییر زمان</DropdownMenuItem>
              <DropdownMenuItem onClick={() => setCanceling(true)}>لغو</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ) : null}
      <ReasonDialog
        title="لغو فعالیت"
        description="فعالیت لغو می‌شود و دلیل در سابقه می‌ماند."
        confirmLabel="لغو فعالیت"
        destructive
        open={canceling}
        onOpenChange={setCanceling}
        onConfirm={cancel}
      />
      {completing ? <CompleteActivityDialog activity={activity} onClose={() => setCompleting(false)} /> : null}
      <ActivityFormDialog activity={activity} open={editing} onOpenChange={setEditing} />
    </div>
  );
}

function Links({ activity }: { activity: Activity }) {
  const { data: me } = useMe();
  const link = activity.deal
    ? { href: `/deals/${activity.deal.id}`, label: activity.deal.name }
    : activity.customer
      ? { href: `/customers/${activity.customer.id}`, label: activity.customer.name }
      : activity.lead
        ? { href: `/leads/${activity.lead.id}`, label: activity.lead.name }
        : null;
  if (!link) return null;
  // Finance team members do not open sales records; the name is enough for context.
  if (me?.finance_member) {
    return <span>{activity.deal && activity.customer ? `${activity.customer.name} — ${link.label}` : link.label}</span>;
  }
  return (
    <Link href={link.href} className="text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
      {activity.deal && activity.customer ? `${activity.customer.name} — ` : ""}
      {link.label}
    </Link>
  );
}

async function invalidateAll(queryClient: ReturnType<typeof useQueryClient>) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: keys.activities }),
    queryClient.invalidateQueries({ queryKey: keys.deals }),
    queryClient.invalidateQueries({ queryKey: keys.timeline }),
    queryClient.invalidateQueries({ queryKey: keys.customers }),
    queryClient.invalidateQueries({ queryKey: keys.leads }),
  ]);
}

/**
 * Finishing an activity (spec 4.2): «انجام شد» with the result, «انجام شد و پیگیری بعدی»
 * which then opens the form for the next step, or «به تأخیر انداختن» to a new date.
 */
export function CompleteActivityDialog({ activity, onClose }: { activity: Activity; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState("");
  const [mode, setMode] = useState<"complete" | "postpone">("complete");
  const [newDate, setNewDate] = useState<string | null>(addDays(todayIso(), 1));
  const [newTime, setNewTime] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [followUp, setFollowUp] = useState(false);

  async function complete(next: boolean) {
    if (!outcome.trim()) {
      setError("نتیجه را بنویسید.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/activities/${activity.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ outcome, version: activity.version }),
      });
      toast.success("فعالیت انجام شد.");
      if (next) {
        // Refresh lists only after the follow-up form closes: the completed activity
        // leaves "open" lists, which would unmount this dialog mid-flow.
        setFollowUp(true);
      } else {
        await invalidateAll(queryClient);
        onClose();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  async function postpone() {
    if (!newDate) return;
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/activities/${activity.id}/postpone`, {
        method: "POST",
        body: JSON.stringify({
          due_date: newDate,
          start_time: newTime || null,
          duration_minutes: newTime ? activity.duration_minutes : null,
          reason: reason || null,
          version: activity.version,
        }),
      });
      await invalidateAll(queryClient);
      toast.success("فعالیت به زمان جدید منتقل شد.");
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  if (followUp) {
    return (
      <ActivityFormDialog
        open
        onOpenChange={(o) => {
          if (!o) {
            void invalidateAll(queryClient);
            onClose();
          }
        }}
        subject={{
          deal: activity.deal ?? undefined,
          customer: activity.deal ? undefined : (activity.customer ?? undefined),
          lead: activity.lead ?? undefined,
        }}
        defaults={{ type: "follow_up", due_date: addDays(todayIso(), 1) }}
        compact
      />
    );
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ActivityTypeIcon type={activity.type} className="size-5" />
            {activity.title}
          </DialogTitle>
          <DialogDescription>
            {whenLabel(activity)} · {activity.owner.full_name}
            {activity.customer ? ` · ${activity.customer.name}` : activity.lead ? ` · ${activity.lead.name}` : ""}
          </DialogDescription>
        </DialogHeader>

        {mode === "complete" ? (
          <Field label="نتیجه" htmlFor="outcome" required>
            <Textarea
              id="outcome"
              autoFocus
              rows={4}
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              placeholder="مثلاً مشتری پیشنهاد را بررسی می‌کند و تا پنجشنبه خبر می‌دهد."
            />
          </Field>
        ) : (
          <div className="space-y-4">
            <Field label="تاریخ جدید" htmlFor="postpone-date" required>
              <JalaliDateInput id="postpone-date" value={newDate} onChange={setNewDate} required />
            </Field>
            <Field label="ساعت" htmlFor="postpone-time">
              <Input id="postpone-time" type="time" dir="ltr" step={300} value={newTime} onChange={(e) => setNewTime(e.target.value)} className="text-start" />
            </Field>
            <Field label="دلیل" htmlFor="postpone-reason">
              <Input id="postpone-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          </div>
        )}

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="ghost" disabled={pending} onClick={() => setMode(mode === "complete" ? "postpone" : "complete")}>
            {mode === "complete" ? "به تأخیر انداختن" : "بازگشت به ثبت نتیجه"}
          </Button>
          {mode === "complete" ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" disabled={pending} onClick={() => void complete(true)}>
                انجام شد و پیگیری بعدی
              </Button>
              <Button disabled={pending} onClick={() => void complete(false)}>
                {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                این فعالیت انجام شد
              </Button>
            </div>
          ) : (
            <Button disabled={pending || !newDate} onClick={() => void postpone()}>
              ثبت زمان جدید
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
