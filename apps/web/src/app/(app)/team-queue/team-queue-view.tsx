"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Hand, Inbox, Loader2, ShieldAlert, UserRoundCheck, X } from "lucide-react";
import { toast } from "sonner";

import { ActivityTypeIcon } from "@/components/crm/activity-bits";
import { Field } from "@/components/crm/bits";
import { Pagination } from "@/components/crm/list-parts";
import { ReasonDialog } from "@/components/crm/reason-dialog";
import { TaskContextView, type TeamTask } from "@/components/crm/team-task-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { dayLabel, todayIso } from "@/lib/jalali";
import { keys, toQuery, useMe } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS, type Page, type UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

type Status = "open" | "assigned" | "canceled";

const TABS: { key: Status; label: string }[] = [
  { key: "open", label: "در انتظار برداشتن" },
  { key: "assigned", label: "واگذارشده" },
  { key: "canceled", label: "لغوشده" },
];

/** A team's queue (spec 4.6): work waits here until a member claims it or the team
 * manager assigns it. */
export function TeamQueueView() {
  const { data: me, isPending } = useMe();
  const [status, setStatus] = useState<Status>("open");
  const [page, setPage] = useState(1);
  const allowed = Boolean(me?.queue_team_ids.length);
  const { data, isPending: loading } = useQuery({
    queryKey: ["team-tasks", "list", status, page],
    queryFn: () => apiFetch<Page<TeamTask>>(`/team-tasks${toQuery({ status, page, page_size: 20 })}`),
    enabled: allowed,
    placeholderData: (previous) => previous,
    refetchInterval: 30_000,
  });

  if (isPending || !me) return <Skeleton className="h-96" />;
  if (!allowed) {
    return (
      <>
        <PageHeader title="صف کار تیم" />
        <Alert>
          <ShieldAlert aria-hidden />
          <AlertTitle>صف کاری برای شما تعریف نشده است</AlertTitle>
          <AlertDescription>صف کار مخصوص اعضا و مدیر تیم مالی است.</AlertDescription>
        </Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="صف کار تیم"
        description="کارهایی که به تیم سپرده شده‌اند. هر عضو می‌تواند کاری را بردارد؛ مدیر تیم می‌تواند آن را به عضوی واگذار کند."
      />
      <div className="flex w-fit flex-wrap gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="وضعیت کارها">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={status === t.key}
            onClick={() => {
              setStatus(t.key);
              setPage(1);
            }}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm",
              status === t.key ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {loading || !data ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </div>
      ) : data.items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
            <Inbox className="size-8 text-muted-foreground" aria-hidden />
            <p className="font-medium">{status === "open" ? "کاری در صف نیست" : "موردی نیست"}</p>
            {status === "open" ? (
              <p className="text-sm text-muted-foreground">کارهای تازه با اعلان خبر داده می‌شوند.</p>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.items.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </div>
          {data.total > data.page_size ? (
            <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          ) : null}
        </>
      )}
    </>
  );
}

function useRefresh() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["team-tasks"] }),
      queryClient.invalidateQueries({ queryKey: keys.activities }),
    ]);
}

function TaskCard({ task }: { task: TeamTask }) {
  const refresh = useRefresh();
  const [claiming, setClaiming] = useState(false);
  const [canceling, setCanceling] = useState(false);
  // Rendered only after the queue has loaded in the browser, so reading the clock is safe.
  const today = todayIso();
  const overdue = task.status === "open" && task.due_date < today;

  async function claim() {
    setClaiming(true);
    try {
      await apiFetch(`/team-tasks/${task.id}/claim`, { method: "POST" });
      toast.success("کار برداشته شد و در فعالیت‌های شما قرار گرفت.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "برداشتن کار انجام نشد.");
    } finally {
      setClaiming(false);
      await refresh();
    }
  }

  async function cancel(reason: string) {
    try {
      await apiFetch(`/team-tasks/${task.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
      toast.success("کار از صف خارج شد.");
      await refresh();
      return true;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
      return false;
    }
  }

  return (
    <Card className="gap-3">
      <CardContent className="space-y-3">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
            <ActivityTypeIcon type={task.type} className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">{task.title}</p>
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>{ACTIVITY_TYPE_LABELS[task.type]}</span>
              <span className={cn("flex items-center gap-1", overdue && "font-medium text-amber-800")}>
                <CalendarClock className="size-3.5" aria-hidden />
                موعد {dayLabel(task.due_date, today)}
              </span>
              <span>صف «{task.team.name}»</span>
            </p>
          </div>
          {overdue ? (
            <Badge variant="secondary" className="bg-warning text-warning-foreground">
              عقب‌افتاده
            </Badge>
          ) : null}
        </div>
        {task.description ? <p className="text-sm text-muted-foreground">{task.description}</p> : null}
        {task.context ? (
          <div className="rounded-lg border bg-muted/30 px-3 py-1">
            <TaskContextView context={task.context} />
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">
          ثبت {formatDateTime(task.created_at)}
          {task.assigned_to ? ` · مسئول: ${task.assigned_to.full_name} (${formatDate(task.assigned_at)})` : ""}
          {task.cancel_reason ? ` · دلیل لغو: ${task.cancel_reason}` : ""}
        </p>
        {task.can_claim || task.can_manage ? (
          <div className="flex flex-wrap gap-2">
            {task.can_claim ? (
              <Button size="sm" disabled={claiming} onClick={() => void claim()}>
                {claiming ? <Loader2 className="animate-spin" aria-hidden /> : <Hand aria-hidden />}
                برمی‌دارم
              </Button>
            ) : null}
            {task.can_manage ? <AssignDialog task={task} onDone={refresh} /> : null}
            {task.can_manage ? (
              <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setCanceling(true)}>
                <X aria-hidden />
                لغو
              </Button>
            ) : null}
          </div>
        ) : null}
        <ReasonDialog
          title="لغو کار صف"
          description="کار از صف خارج می‌شود و دلیل آن می‌ماند."
          confirmLabel="لغو کار"
          destructive
          open={canceling}
          onOpenChange={setCanceling}
          onConfirm={cancel}
        />
      </CardContent>
    </Card>
  );
}

function AssignDialog({ task, onDone }: { task: TeamTask; onDone: () => Promise<unknown> }) {
  const [open, setOpen] = useState(false);
  const [userId, setUserId] = useState("");
  const [pending, setPending] = useState(false);
  const { data: members } = useQuery({
    queryKey: ["team-tasks", task.id, "members"],
    queryFn: () => apiFetch<UserRef[]>(`/team-tasks/${task.id}/members`),
    enabled: open,
  });

  async function assign() {
    setPending(true);
    try {
      await apiFetch(`/team-tasks/${task.id}/assign`, { method: "POST", body: JSON.stringify({ user_id: userId }) });
      toast.success("کار واگذار شد.");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "واگذاری انجام نشد.");
    } finally {
      setPending(false);
      await onDone();
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setUserId("");
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <UserRoundCheck aria-hidden />
            واگذاری
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>واگذاری کار</DialogTitle>
          <DialogDescription>«{task.title}» به عضوی از تیم «{task.team.name}» سپرده می‌شود.</DialogDescription>
        </DialogHeader>
        <Field label="عضو تیم" htmlFor="assign-member" required>
          <NativeSelect id="assign-member" className="w-full" value={userId} onChange={(e) => setUserId(e.target.value)}>
            <NativeSelectOption value="">{members ? "انتخاب کنید" : "در حال دریافت…"}</NativeSelectOption>
            {(members ?? []).map((m) => (
              <NativeSelectOption key={m.id} value={m.id}>
                {m.full_name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <DialogFooter>
          <Button disabled={!userId || pending} onClick={() => void assign()}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            واگذاری
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
