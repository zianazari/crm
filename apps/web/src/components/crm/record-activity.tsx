"use client";

import { useState } from "react";
import {
  Banknote,
  CalendarPlus,
  CircleCheck,
  CircleX,
  GitCommitHorizontal,
  History,
  Loader2,
  StickyNote,
  type LucideIcon,
  Send,
} from "lucide-react";
import { UserAvatar } from "@/components/crm/user-avatar";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";
import { ActivityItem, ActivityTypeIcon } from "@/components/crm/activity-bits";
import { SendMessageDialog } from "@/components/crm/send-message-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { formatIsoDate, formatTime } from "@/lib/jalali";
import { keys, useActivities, useTimeline, type TimelineSubject } from "@/lib/queries";
import type { ActivitySubject, TimelineEntry, TimelineKind } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Planned (open) activities of a record, with a button to plan another one. */
export function PlannedActivities({ subject, filter }: { subject: ActivitySubject; filter: TimelineSubject }) {
  const { data, isPending } = useActivities({ ...filter, status: "open", page_size: 50 });
  const items = data?.items ?? [];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <CalendarPlus className="size-5" aria-hidden />
          فعالیت‌های برنامه‌ریزی‌شده
        </CardTitle>
        <ActivityFormDialog
          subject={subject}
          trigger={
            <Button size="sm">
              <CalendarPlus aria-hidden />
              فعالیت جدید
            </Button>
          }
        />
      </CardHeader>
      <CardContent className="space-y-2">
        {isPending ? (
          <p className="text-sm text-muted-foreground">در حال دریافت…</p>
        ) : items.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            پیگیری بعدی برنامه‌ریزی نشده است.
          </p>
        ) : (
          items.map((a) => <ActivityItem key={a.id} activity={a} showLinks={false} />)
        )}
      </CardContent>
    </Card>
  );
}

const FILTERS: { label: string; kinds: TimelineKind[] | null }[] = [
  { label: "همه", kinds: null },
  { label: "فعالیت‌ها", kinds: ["activity"] },
  { label: "یادداشت‌ها", kinds: ["note"] },
  { label: "پیام‌ها", kinds: ["message"] },
  { label: "مراحل و پرداخت‌ها", kinds: ["stage", "payment"] },
];

/** Everything that happened on a record, newest first (spec 4.3 deal file). */
export function Timeline({ subject, title = "سابقه پیگیری‌ها" }: { subject: TimelineSubject; title?: string }) {
  const [filter, setFilter] = useState(0);
  const { data, isPending, fetchNextPage, hasNextPage, isFetchingNextPage } = useTimeline(subject, FILTERS[filter].kinds);
  const entries = data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <History className="size-5" aria-hidden />
            {title}
          </CardTitle>
          <SendMessageDialog subject={subject} />
        </div>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="نوع رویداد">
          {FILTERS.map((f, i) => (
            <button
              key={f.label}
              role="tab"
              aria-selected={filter === i}
              onClick={() => setFilter(i)}
              className={cn(
                "rounded-full border px-3 py-1 text-sm",
                filter === i ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <NoteComposer subject={subject} />
        {isPending ? (
          <p className="text-sm text-muted-foreground">در حال دریافت…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">هنوز سابقه‌ای ثبت نشده است.</p>
        ) : (
          <ol className="space-y-3 border-s ps-5">
            {entries.map((e) => (
              <TimelineItem key={`${e.kind}-${e.id}`} entry={e} />
            ))}
          </ol>
        )}
        {hasNextPage ? (
          <Button variant="outline" size="sm" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
            {isFetchingNextPage ? <Loader2 className="animate-spin" aria-hidden /> : null}
            موارد قدیمی‌تر
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

const KIND_ICONS: Record<TimelineKind, LucideIcon> = {
  activity: CircleCheck,
  note: StickyNote,
  stage: GitCommitHorizontal,
  payment: Banknote,
  message: Send,
};

const MESSAGE_STATUS: Record<string, string> = {
  queued: "در صف",
  sending: "در صف",
  accepted: "پذیرفته‌شده توسط سرویس‌دهنده",
  delivered: "تحویل‌شده",
  failed: "ناموفق",
  unknown: "نامشخص",
  canceled: "لغو شد",
};

function TimelineItem({ entry }: { entry: TimelineEntry }) {
  const a = entry.activity;
  const canceled = a?.status === "canceled";
  const Icon = canceled ? CircleX : KIND_ICONS[entry.kind];
  return (
    <li className="relative">
      <span
        className={cn(
          "absolute -start-[1.85rem] top-0.5 grid size-6 place-items-center rounded-full border-2 border-background",
          canceled ? "bg-muted text-muted-foreground" : "bg-accent text-accent-foreground",
        )}
        aria-hidden
      >
        <Icon className="size-3.5" />
      </span>
      <div className="rounded-lg border bg-card p-3 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="flex items-center gap-1.5 font-medium">
            {a ? <ActivityTypeIcon type={a.type} className="size-4 text-muted-foreground" /> : null}
            {entry.title}
            {canceled ? <span className="text-xs font-normal text-muted-foreground">(لغو شد)</span> : null}
            {entry.message_status ? (
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[11px] font-normal",
                  entry.message_status === "delivered"
                    ? "bg-success text-success-foreground"
                    : entry.message_status === "failed" || entry.message_status === "canceled"
                      ? "bg-destructive/10 text-destructive"
                      : "bg-muted text-muted-foreground",
                )}
              >
                {MESSAGE_STATUS[entry.message_status] ?? entry.message_status}
              </span>
            ) : null}
          </p>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <UserAvatar user={entry.actor} className="size-6" />
            {entry.actor.full_name} · {formatDateTime(entry.at)}
          </p>
        </div>
        {entry.deal ? <p className="text-xs text-muted-foreground">فروش: {entry.deal.name}</p> : null}
        {entry.body ? <p className="mt-1 whitespace-pre-line leading-7 text-muted-foreground">{entry.body}</p> : null}
        {a && a.status === "done" ? (
          <p className="mt-1 text-xs text-muted-foreground">
            برنامه: {formatIsoDate(a.due_date)}
            {a.start_at ? ` ${formatTime(a.start_at)}` : ""} · مسئول: {a.owner.full_name} · ثبت‌کننده:{" "}
            {a.created_by.full_name}
          </p>
        ) : null}
      </div>
    </li>
  );
}

function NoteComposer({ subject }: { subject: TimelineSubject }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      await apiFetch("/notes", { method: "POST", body: JSON.stringify({ body, ...subject }) });
      setBody("");
      await queryClient.invalidateQueries({ queryKey: keys.timeline });
      toast.success("یادداشت ثبت شد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-2">
      <Textarea
        rows={2}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="یادداشت داخلی… (برای مشتری ارسال نمی‌شود)"
        aria-label="یادداشت جدید"
      />
      {body.trim() ? (
        <Button size="sm" disabled={pending} onClick={() => void save()}>
          {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          ثبت یادداشت
        </Button>
      ) : null}
    </div>
  );
}
