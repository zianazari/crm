"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import { Loader2, Maximize2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ActivityTypeIcon } from "@/components/crm/activity-bits";
import { Field } from "@/components/crm/bits";
import { CustomerPicker } from "@/components/crm/customer-picker";
import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { formatTime, hhmm, minutesOfDay, todayIso } from "@/lib/jalali";
import { keys, useAssignableUsers, useDeals, useMe, useOwnerDay } from "@/lib/queries";
import {
  ACTIVITY_TYPE_LABELS,
  PRIORITY_LABELS,
  type Activity,
  type ActivitySubject,
  type ActivityType,
  type CustomerFull,
  type Priority,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export type ActivityDefaults = {
  type?: ActivityType;
  title?: string;
  due_date?: string;
  start_time?: string | null;
  duration_minutes?: number | null;
};

type Values = {
  type: ActivityType;
  title: string;
  due_date: string | null;
  start_time: string;
  duration_minutes: number | null;
  owner_id: string;
  priority: Priority;
  reminder_minutes: number | null;
  description: string;
  customer: CustomerFull | null;
  deal_id: string;
};

const DURATIONS = [15, 30, 45, 60, 90, 120, 180];
const REMINDERS: { value: number | null; label: string }[] = [
  { value: null, label: "بدون یادآوری" },
  { value: 0, label: "هنگام شروع" },
  { value: 15, label: "۱۵ دقیقه قبل" },
  { value: 60, label: "یک ساعت قبل" },
  { value: 24 * 60, label: "یک روز قبل" },
];

/** ``resolveToday``: fill in today's date. Only done once the dialog opens, because
 * reading the clock while a page is prerendered is not allowed. */
function initialValues(activity?: Activity, defaults?: ActivityDefaults, resolveToday = true): Values {
  return {
    type: activity?.type ?? defaults?.type ?? "call",
    title: activity?.title ?? defaults?.title ?? "",
    due_date: activity?.due_date ?? defaults?.due_date ?? (resolveToday ? todayIso() : null),
    start_time: activity?.start_at ? hhmm(activity.start_at) : (defaults?.start_time ?? ""),
    duration_minutes: activity?.duration_minutes ?? defaults?.duration_minutes ?? null,
    owner_id: activity?.owner.id ?? "",
    priority: activity?.priority ?? "normal",
    reminder_minutes: activity?.reminder_minutes ?? null,
    description: activity?.description ?? "",
    customer: null,
    deal_id: "",
  };
}

/**
 * Create or edit an activity. ``compact`` starts with the quick form (type, title,
 * date, optional time); «فرم کامل» expands it without losing what was typed.
 * ``subject`` fixes the record the activity belongs to (deal, customer or lead).
 */
export function ActivityFormDialog({
  activity,
  subject,
  defaults,
  compact = false,
  trigger,
  open: controlledOpen,
  onOpenChange,
}: {
  activity?: Activity;
  subject?: ActivitySubject;
  defaults?: ActivityDefaults;
  compact?: boolean;
  trigger?: ReactElement;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: assignable = [] } = useAssignableUsers();
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const [values, setValues] = useState<Values>(() => initialValues(activity, defaults, controlledOpen === true));
  const [full, setFull] = useState(!compact);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const editing = Boolean(activity);
  const fixedSubject = Boolean(subject && (subject.deal || subject.customer || subject.lead));

  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  function changeOpen(next: boolean) {
    if (next) {
      setValues(initialValues(activity, defaults));
      setFull(!compact);
      setError(null);
    }
    setInternalOpen(next);
    onOpenChange?.(next);
  }

  async function submit(event: FormEvent | null, again: boolean) {
    event?.preventDefault();
    setError(null);
    if (!values.due_date) {
      setError("تاریخ را انتخاب کنید.");
      return;
    }
    setPending(true);
    const schedule = {
      due_date: values.due_date,
      start_time: values.start_time || null,
      duration_minutes: values.start_time ? values.duration_minutes : null,
    };
    const common = {
      type: values.type,
      title: values.title.trim() || ACTIVITY_TYPE_LABELS[values.type],
      description: values.description || null,
      priority: values.priority,
      reminder_minutes: values.reminder_minutes,
      ...schedule,
    };
    try {
      if (editing) {
        await apiFetch(`/activities/${activity!.id}`, {
          method: "PATCH",
          body: JSON.stringify({ ...common, owner_id: values.owner_id || null, version: activity!.version }),
        });
      } else {
        await apiFetch("/activities", {
          method: "POST",
          body: JSON.stringify({
            ...common,
            owner_id: values.owner_id || null,
            deal_id: subject?.deal?.id ?? (values.deal_id || null),
            customer_id: subject?.customer?.id ?? values.customer?.id ?? null,
            lead_id: subject?.lead?.id ?? null,
          }),
        });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.activities }),
        queryClient.invalidateQueries({ queryKey: keys.deals }),
        queryClient.invalidateQueries({ queryKey: keys.timeline }),
      ]);
      toast.success(editing ? "فعالیت به‌روز شد." : "فعالیت ثبت شد.");
      if (again) {
        setValues((v) => ({ ...v, title: "", start_time: "", description: "" }));
      } else {
        changeOpen(false);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  const ownerId = values.owner_id || me?.id;
  const subjectLabel = subject?.deal?.name ?? subject?.customer?.name ?? subject?.lead?.name;

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      {trigger ? <DialogTrigger render={trigger} /> : null}
      <DialogContent className={cn("max-h-[92svh] overflow-y-auto", full ? "sm:max-w-4xl" : "sm:max-w-md")}>
        <DialogHeader>
          <DialogTitle>{editing ? "ویرایش فعالیت" : "فعالیت جدید"}</DialogTitle>
          <DialogDescription>
            {subjectLabel ? `برای «${subjectLabel}»` : "فعالیت بدون ساعت زمان تقویم را اشغال نمی‌کند."}
          </DialogDescription>
        </DialogHeader>

        <div className={cn("grid gap-6", full && "md:grid-cols-[1fr_16rem]")}>
          <form id="activity-form" onSubmit={(e) => void submit(e, false)} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2" role="radiogroup" aria-label="نوع فعالیت">
              <div className="grid grid-cols-4 gap-1.5">
                {(Object.keys(ACTIVITY_TYPE_LABELS) as ActivityType[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="radio"
                    aria-checked={values.type === t}
                    onClick={() => set("type", t)}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-lg border py-2 text-xs",
                      values.type === t ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <ActivityTypeIcon type={t} className="size-4" />
                    {ACTIVITY_TYPE_LABELS[t]}
                  </button>
                ))}
              </div>
            </div>
            <Field label="عنوان" htmlFor="act-title" className="sm:col-span-2">
              <Input
                id="act-title"
                autoFocus
                value={values.title}
                onChange={(e) => set("title", e.target.value)}
                placeholder={ACTIVITY_TYPE_LABELS[values.type]}
              />
            </Field>
            <Field label="تاریخ" htmlFor="act-date" required>
              <JalaliDateInput id="act-date" value={values.due_date} onChange={(v) => set("due_date", v)} required />
            </Field>
            <Field label="ساعت" htmlFor="act-time" hint="خالی یعنی بدون ساعت مشخص.">
              <Input
                id="act-time"
                type="time"
                dir="ltr"
                step={300}
                value={values.start_time}
                onChange={(e) => set("start_time", e.target.value)}
                className="text-start"
              />
            </Field>

            {full ? (
              <>
                <Field label="مدت" htmlFor="act-duration">
                  <NativeSelect
                    id="act-duration"
                    disabled={!values.start_time}
                    value={values.duration_minutes ?? ""}
                    onChange={(e) => set("duration_minutes", e.target.value ? Number(e.target.value) : null)}
                    className="w-full"
                  >
                    <NativeSelectOption value="">نامشخص</NativeSelectOption>
                    {DURATIONS.map((d) => (
                      <NativeSelectOption key={d} value={d}>
                        {formatNumber(d)} دقیقه
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="مسئول انجام" htmlFor="act-owner">
                  <NativeSelect
                    id="act-owner"
                    value={values.owner_id}
                    onChange={(e) => set("owner_id", e.target.value)}
                    className="w-full"
                    disabled={assignable.length <= 1}
                  >
                    <NativeSelectOption value="">خودم</NativeSelectOption>
                    {assignable
                      .filter((u) => u.id !== me?.id)
                      .map((u) => (
                        <NativeSelectOption key={u.id} value={u.id}>
                          {u.full_name}
                        </NativeSelectOption>
                      ))}
                  </NativeSelect>
                </Field>
                <Field label="اولویت" htmlFor="act-priority">
                  <NativeSelect
                    id="act-priority"
                    value={values.priority}
                    onChange={(e) => set("priority", e.target.value as Priority)}
                    className="w-full"
                  >
                    {(Object.keys(PRIORITY_LABELS) as Priority[]).map((p) => (
                      <NativeSelectOption key={p} value={p}>
                        {PRIORITY_LABELS[p]}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="یادآوری" htmlFor="act-reminder">
                  <NativeSelect
                    id="act-reminder"
                    value={values.reminder_minutes ?? ""}
                    onChange={(e) => set("reminder_minutes", e.target.value === "" ? null : Number(e.target.value))}
                    className="w-full"
                  >
                    {REMINDERS.map((r) => (
                      <NativeSelectOption key={r.label} value={r.value ?? ""}>
                        {r.label}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                {!editing && !fixedSubject ? <SubjectPicker values={values} set={set} /> : null}
                <Field label="توضیحات" htmlFor="act-description" className="sm:col-span-2">
                  <Textarea
                    id="act-description"
                    rows={3}
                    value={values.description}
                    onChange={(e) => set("description", e.target.value)}
                  />
                </Field>
              </>
            ) : null}
          </form>

          {full ? <DayPanel ownerId={ownerId} day={values.due_date} chosenTime={values.start_time} editingId={activity?.id} /> : null}
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter className="gap-2 sm:justify-between">
          {!full ? (
            <Button type="button" variant="ghost" onClick={() => setFull(true)}>
              <Maximize2 aria-hidden />
              فرم کامل
            </Button>
          ) : (
            <span />
          )}
          <div className="flex flex-wrap gap-2">
            {!editing ? (
              <Button type="button" variant="outline" disabled={pending} onClick={() => void submit(null, true)}>
                ذخیره و ساخت فعالیت دیگر
              </Button>
            ) : null}
            <Button type="submit" form="activity-form" disabled={pending}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              ذخیره
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SubjectPicker({
  values,
  set,
}: {
  values: Values;
  set: <K extends keyof Values>(key: K, value: Values[K]) => void;
}) {
  const { data } = useDeals({ customer_id: values.customer?.id, status: "open", page_size: 50 });
  const deals = values.customer ? (data?.items ?? []).filter((d) => d.access === "full") : [];
  return (
    <>
      <Field label="مشتری" className="sm:col-span-2" hint="اختیاری؛ فعالیت در پرونده همین مشتری دیده می‌شود.">
        <CustomerPicker
          value={values.customer}
          onChange={(c) => {
            set("customer", c);
            set("deal_id", "");
          }}
        />
      </Field>
      {deals.length ? (
        <Field label="فروش مرتبط" htmlFor="act-deal" className="sm:col-span-2">
          <NativeSelect id="act-deal" value={values.deal_id} onChange={(e) => set("deal_id", e.target.value)} className="w-full">
            <NativeSelectOption value="">بدون فروش</NativeSelectOption>
            {deals.map((d) => (
              <NativeSelectOption key={d.id} value={d.id}>
                {d.title}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
      ) : null}
    </>
  );
}

/** The selected person's schedule for the chosen day, beside the form (spec 4.2). */
function DayPanel({
  ownerId,
  day,
  chosenTime,
  editingId,
}: {
  ownerId: string | undefined;
  day: string | null;
  chosenTime: string;
  editingId?: string;
}) {
  const { data: items = [], isPending } = useOwnerDay(ownerId, day);
  const chosen = chosenTime ? Number(chosenTime.slice(0, 2)) * 60 + Number(chosenTime.slice(3, 5)) : null;
  const others = items.filter((a) => a.id !== editingId);

  return (
    <aside className="rounded-lg border bg-muted/30 p-3 text-sm" aria-label="برنامه همان روز">
      <p className="mb-2 font-medium">برنامه همان روز</p>
      {isPending ? (
        <p className="text-xs text-muted-foreground">در حال دریافت…</p>
      ) : others.length === 0 ? (
        <p className="text-xs text-muted-foreground">برنامه‌ای ثبت نشده است.</p>
      ) : (
        <ul className="space-y-1.5">
          {others.map((a) => {
            const start = a.start_at ? minutesOfDay(a.start_at) : null;
            const end = start !== null ? start + (a.duration_minutes ?? 30) : null;
            const clash = chosen !== null && start !== null && end !== null && chosen >= start && chosen < end;
            return (
              <li
                key={a.id}
                className={cn(
                  "flex items-start gap-2 rounded-md border bg-card px-2 py-1.5",
                  clash && "border-warning-foreground/40 bg-warning",
                )}
              >
                <ActivityTypeIcon type={a.type} className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{a.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {a.start_at ? formatTime(a.start_at) : "بدون ساعت"}
                    {a.duration_minutes ? ` · ${formatNumber(a.duration_minutes)} دقیقه` : ""}
                  </span>
                </span>
                {clash ? <span className="text-xs text-warning-foreground">هم‌پوشانی</span> : null}
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
