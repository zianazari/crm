"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2, Info, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { CancelBookingDialog } from "@/components/booking/cancel-booking-dialog";
import { formatSlot, SlotPicker } from "@/components/booking/slot-picker";
import { Field } from "@/components/crm/bits";
import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import type { BookingSettings, MeetingType, Rule, Slots, StaffBooking } from "@/lib/booking";
import { formatNumber } from "@/lib/format";
import { formatIsoDate, todayIso, WEEKDAYS } from "@/lib/jalali";
import { canManage, toQuery, useAssignableUsers, useMe } from "@/lib/queries";
import { useHydrated } from "@/lib/use-hydrated";

const settingsKey = (userId: string | null) => ["booking", "settings", userId ?? "me"];

export function AvailabilityView() {
  const { data: me } = useMe();
  const hydrated = useHydrated();
  const manager = hydrated && canManage(me?.role);
  const { data: users = [] } = useAssignableUsers();
  const [userId, setUserId] = useState<string | null>(null);
  const { data: settings, error } = useQuery({
    queryKey: settingsKey(userId),
    queryFn: () => apiFetch<BookingSettings>(`/booking/settings${toQuery({ user_id: userId })}`),
  });

  return (
    <>
      <PageHeader
        title="زمان‌های رزرو"
        description="ساعت کاری، نوع جلسه و روزهای تعطیل؛ مشتری با لینک اختصاصی فقط زمان‌های آزاد همین تقویم را می‌بیند."
        actions={
          manager && users.length > 1 ? (
            <Field label="تقویم" htmlFor="calendar-owner" className="min-w-52">
              <NativeSelect id="calendar-owner" className="w-full" value={userId ?? ""} onChange={(e) => setUserId(e.target.value || null)}>
                <NativeSelectOption value="">تقویم خودم</NativeSelectOption>
                {users
                  .filter((u) => u.id !== me?.id)
                  .map((u) => (
                    <NativeSelectOption key={u.id} value={u.id}>
                      {u.full_name}
                    </NativeSelectOption>
                  ))}
              </NativeSelect>
            </Field>
          ) : null
        }
      />
      <p className="flex items-start gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        زمان آزاد فقط از روی تقویم همین CRM حساب می‌شود: فعالیت‌های ساعت‌دار باز و جلسه‌های رزروشده. تقویم‌های بیرونی هنوز
        وصل نیستند، پس قرارهایی را که فقط جای دیگری ثبت کرده‌اید این‌جا هم به‌صورت فعالیت ثبت کنید.
      </p>
      {error ? (
        <p className="text-sm text-destructive">{error instanceof ApiError ? error.message : "بارگیری نشد."}</p>
      ) : !settings ? (
        <Skeleton className="h-96" />
      ) : (
        <div key={settings.user.id} className="grid items-start gap-6 lg:grid-cols-2">
          <div className="min-w-0 space-y-6">
            <HoursCard settings={settings} userId={userId} />
            <UpcomingCard userId={settings.user.id} />
          </div>
          <div className="min-w-0 space-y-6">
            <MeetingTypesCard settings={settings} userId={userId} />
            <DaysOffCard settings={settings} userId={userId} isAdmin={me?.role === "admin"} />
            <PreviewCard settings={settings} />
          </div>
        </div>
      )}
    </>
  );
}

// -- hours and rules ----------------------------------------------------------------------

type DayRanges = Record<number, { start: string; end: string }[]>;

function toRanges(rules: Rule[]): DayRanges {
  const days: DayRanges = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
  for (const r of rules) days[r.weekday].push({ start: r.start, end: r.end });
  return days;
}

function HoursCard({ settings, userId }: { settings: BookingSettings; userId: string | null }) {
  const queryClient = useQueryClient();
  const [days, setDays] = useState<DayRanges>(() => toRanges(settings.rules));
  const [numbers, setNumbers] = useState({
    buffer_before_minutes: settings.buffer_before_minutes,
    buffer_after_minutes: settings.buffer_after_minutes,
    min_notice_hours: Math.round(settings.min_notice_minutes / 60),
    horizon_days: settings.horizon_days,
    change_deadline_hours: settings.change_deadline_hours,
  });
  const [pending, setPending] = useState(false);

  function setRange(day: number, index: number, key: "start" | "end", value: string) {
    setDays((d) => ({ ...d, [day]: d[day].map((r, i) => (i === index ? { ...r, [key]: value } : r)) }));
  }

  async function save() {
    setPending(true);
    try {
      const rules = Object.entries(days).flatMap(([weekday, ranges]) =>
        ranges.map((r) => ({ weekday: Number(weekday), start: r.start, end: r.end })),
      );
      const saved = await apiFetch<BookingSettings>(`/booking/settings${toQuery({ user_id: userId })}`, {
        method: "PUT",
        body: JSON.stringify({
          buffer_before_minutes: numbers.buffer_before_minutes,
          buffer_after_minutes: numbers.buffer_after_minutes,
          min_notice_minutes: numbers.min_notice_hours * 60,
          horizon_days: numbers.horizon_days,
          change_deadline_hours: numbers.change_deadline_hours,
          rules,
        }),
      });
      queryClient.setQueryData(settingsKey(userId), saved);
      void queryClient.invalidateQueries({ queryKey: ["booking", "slots"] });
      toast.success("تنظیمات ذخیره شد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ذخیره نشد.");
    } finally {
      setPending(false);
    }
  }

  const number = (key: keyof typeof numbers, label: string, unit: string, max: number) => (
    <Field label={`${label} (${unit})`} htmlFor={`n-${key}`}>
      <Input
        id={`n-${key}`}
        type="number"
        dir="ltr"
        min={0}
        max={max}
        value={numbers[key]}
        onChange={(e) => setNumbers((n) => ({ ...n, [key]: Math.max(0, Math.min(max, Number(e.target.value) || 0)) }))}
      />
    </Field>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>ساعت کاری و قواعد رزرو</CardTitle>
        <CardDescription>شروع جلسه‌ها روی ساعت و نیم ساعتِ این بازه‌هاست.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <ul className="divide-y rounded-lg border">
          {WEEKDAYS.map((name, day) => (
            <li key={name} className="flex flex-wrap items-start gap-3 px-3 py-2.5">
              <label className="flex w-28 items-center gap-2 pt-1.5 text-sm font-medium">
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={days[day].length > 0}
                  onChange={(e) =>
                    setDays((d) => ({ ...d, [day]: e.target.checked ? [{ start: "09:00", end: "17:00" }] : [] }))
                  }
                />
                {name}
              </label>
              <div className="min-w-0 flex-1 space-y-2">
                {days[day].length === 0 ? <p className="pt-1.5 text-sm text-muted-foreground">تعطیل</p> : null}
                {days[day].map((r, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    <TimeSelect label={`شروع ${name}`} value={r.start} onChange={(v) => setRange(day, i, "start", v)} />
                    <span className="text-sm text-muted-foreground">تا</span>
                    <TimeSelect label={`پایان ${name}`} value={r.end} onChange={(v) => setRange(day, i, "end", v)} />
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="حذف بازه"
                      onClick={() => setDays((d) => ({ ...d, [day]: d[day].filter((_, j) => j !== i) }))}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  </div>
                ))}
                {days[day].length > 0 && days[day].length < 4 ? (
                  <Button
                    variant="link"
                    size="sm"
                    className="h-auto px-0"
                    onClick={() => setDays((d) => ({ ...d, [day]: [...d[day], { start: "14:00", end: "18:00" }] }))}
                  >
                    <Plus aria-hidden />
                    بازه دیگر
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
        <div className="grid gap-3 sm:grid-cols-2">
          {number("buffer_before_minutes", "فاصله پیش از جلسه", "دقیقه", 240)}
          {number("buffer_after_minutes", "فاصله پس از جلسه", "دقیقه", 240)}
          {number("min_notice_hours", "حداقل فاصله تا رزرو", "ساعت", 336)}
          {number("horizon_days", "رزرو تا چند روز جلوتر", "روز", 180)}
          {number("change_deadline_hours", "مهلت لغو یا تغییر توسط مشتری", "ساعت پیش از جلسه", 336)}
        </div>
        <div className="flex justify-end">
          <Button onClick={() => void save()} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

const HALF_HOURS = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 ? "30" : "00"}`);
const faTime = (t: string) => t.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);

function TimeSelect({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const options = HALF_HOURS.includes(value) ? HALF_HOURS : [value, ...HALF_HOURS];
  return (
    <NativeSelect aria-label={label} className="w-24" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((t) => (
        <NativeSelectOption key={t} value={t}>
          {faTime(t)}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  );
}

// -- meeting types --------------------------------------------------------------------------

function MeetingTypesCard({ settings, userId }: { settings: BookingSettings; userId: string | null }) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <CardTitle>انواع جلسه</CardTitle>
          <CardDescription>عنوان، مدت و توضیحی که مشتری می‌بیند (مثلاً نشانی یا نحوه تماس).</CardDescription>
        </div>
        <MeetingTypeDialog userId={userId} />
      </CardHeader>
      <CardContent>
        <ul className="divide-y rounded-lg border">
          {settings.meeting_types.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
              <div className="min-w-0">
                <p className="font-medium">
                  {t.title}
                  {!t.is_active ? <span className="ms-2 text-xs font-normal text-muted-foreground">(غیرفعال)</span> : null}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatNumber(t.duration_minutes)} دقیقه{t.description ? ` · ${t.description}` : ""}
                </p>
              </div>
              <MeetingTypeDialog userId={userId} meeting={t} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function MeetingTypeDialog({ userId, meeting }: { userId: string | null; meeting?: MeetingType }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", duration: 30, description: "", active: true });
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      const body = { title: form.title.trim(), duration_minutes: form.duration, description: form.description.trim() || null };
      await apiFetch(meeting ? `/booking/meeting-types/${meeting.id}` : `/booking/meeting-types${toQuery({ user_id: userId })}`, {
        method: meeting ? "PATCH" : "POST",
        body: JSON.stringify(meeting ? { ...body, is_active: form.active } : body),
      });
      await queryClient.invalidateQueries({ queryKey: ["booking"] });
      toast.success("نوع جلسه ذخیره شد.");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ذخیره نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next)
          setForm({
            title: meeting?.title ?? "",
            duration: meeting?.duration_minutes ?? 30,
            description: meeting?.description ?? "",
            active: meeting?.is_active ?? true,
          });
      }}
    >
      <DialogTrigger
        render={
          meeting ? (
            <Button variant="ghost" size="sm">
              ویرایش
            </Button>
          ) : (
            <Button variant="outline" size="sm">
              <Plus aria-hidden />
              نوع جلسه
            </Button>
          )
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{meeting ? "ویرایش نوع جلسه" : "نوع جلسه تازه"}</DialogTitle>
          <DialogDescription>لینک‌های قبلیِ این نوع جلسه هم از مدت تازه استفاده می‌کنند.</DialogDescription>
        </DialogHeader>
        <Field label="عنوان" htmlFor="mt-title" required>
          <Input id="mt-title" maxLength={120} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <Field label="مدت" htmlFor="mt-duration" required>
          <NativeSelect id="mt-duration" className="w-full" value={String(form.duration)} onChange={(e) => setForm({ ...form, duration: Number(e.target.value) })}>
            {[15, 20, 30, 45, 60, 90, 120].map((m) => (
              <NativeSelectOption key={m} value={String(m)}>
                {formatNumber(m)} دقیقه
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field label="توضیح برای مشتری" htmlFor="mt-description" hint="مثلاً «حضوری در دفتر» یا «تماس تصویری؛ لینک پیش از جلسه فرستاده می‌شود».">
          <Textarea id="mt-description" rows={3} maxLength={500} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        {meeting ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />
            فعال (برای لینک‌های تازه قابل انتخاب است)
          </label>
        ) : null}
        <DialogFooter>
          <Button onClick={() => void save()} disabled={pending || form.title.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -- days off -------------------------------------------------------------------------------

function DaysOffCard({ settings, userId, isAdmin }: { settings: BookingSettings; userId: string | null; isAdmin: boolean }) {
  const queryClient = useQueryClient();

  async function remove(id: string) {
    try {
      await apiFetch(`/booking/exceptions/${id}`, { method: "DELETE" });
      await queryClient.invalidateQueries({ queryKey: ["booking"] });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "حذف نشد.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <CardTitle>مرخصی و تعطیلات</CardTitle>
          <CardDescription>روزهای کامل که رزرو نمی‌شوند. تعطیلات سازمان را ادمین ثبت می‌کند.</CardDescription>
        </div>
        <DayOffDialog userId={userId} isAdmin={isAdmin} />
      </CardHeader>
      <CardContent>
        {settings.exceptions.length === 0 ? (
          <p className="text-sm text-muted-foreground">موردی ثبت نشده است.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {settings.exceptions.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                <span>
                  {formatIsoDate(e.start_date)}
                  {e.end_date !== e.start_date ? ` تا ${formatIsoDate(e.end_date)}` : ""} — {e.reason}
                  {e.organization ? <span className="ms-2 rounded bg-muted px-1.5 py-0.5 text-[11px]">تعطیل سازمان</span> : null}
                </span>
                {!e.organization || isAdmin ? (
                  <Button variant="ghost" size="icon-sm" aria-label={`حذف ${e.reason}`} onClick={() => void remove(e.id)}>
                    <Trash2 aria-hidden />
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DayOffDialog({ userId, isAdmin }: { userId: string | null; isAdmin: boolean }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState<string | null>(todayIso());
  const [end, setEnd] = useState<string | null>(todayIso());
  const [reason, setReason] = useState("");
  const [organization, setOrganization] = useState(false);
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      await apiFetch(`/booking/exceptions${toQuery({ user_id: userId })}`, {
        method: "POST",
        body: JSON.stringify({ start_date: start, end_date: end, reason: reason.trim(), organization }),
      });
      await queryClient.invalidateQueries({ queryKey: ["booking"] });
      toast.success("ثبت شد.");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ثبت نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setStart(todayIso());
          setEnd(todayIso());
          setReason("");
          setOrganization(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            <Plus aria-hidden />
            روز تعطیل
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>مرخصی یا تعطیلی</DialogTitle>
          <DialogDescription>در این روزها هیچ زمانی به مشتری نشان داده نمی‌شود.</DialogDescription>
        </DialogHeader>
        <Field label="از" htmlFor="off-start" required>
          <JalaliDateInput id="off-start" value={start} onChange={(v) => { setStart(v); if (v && end && end < v) setEnd(v); }} required />
        </Field>
        <Field label="تا" htmlFor="off-end" required>
          <JalaliDateInput id="off-end" value={end} onChange={setEnd} required />
        </Field>
        <Field label="عنوان" htmlFor="off-reason" required>
          <Input id="off-reason" maxLength={200} placeholder="مثلاً مرخصی یا تعطیل رسمی" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {isAdmin ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={organization} onChange={(e) => setOrganization(e.target.checked)} />
            تعطیل برای همه سازمان
          </label>
        ) : null}
        <DialogFooter>
          <Button onClick={() => void save()} disabled={pending || !start || !end || end < start || reason.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// -- preview and upcoming -------------------------------------------------------------------

function PreviewCard({ settings }: { settings: BookingSettings }) {
  const active = settings.meeting_types.filter((t) => t.is_active);
  const [typeId, setTypeId] = useState(active[0]?.id ?? "");
  const { data } = useQuery({
    queryKey: ["booking", "slots", typeId],
    queryFn: () => apiFetch<Slots>(`/booking/slots?meeting_type_id=${typeId}`),
    enabled: Boolean(typeId),
  });
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <CardTitle>آنچه مشتری می‌بیند</CardTitle>
          <CardDescription>زمان‌های آزاد همین حالا، با همه قواعد و فعالیت‌های ثبت‌شده.</CardDescription>
        </div>
        {active.length > 1 ? (
          <NativeSelect aria-label="نوع جلسه" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            {active.map((t) => (
              <NativeSelectOption key={t.id} value={t.id}>
                {t.title}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : null}
      </CardHeader>
      <CardContent>
        {!typeId ? (
          <p className="text-sm text-muted-foreground">نوع جلسه فعالی نیست.</p>
        ) : !data ? (
          <Skeleton className="h-40" />
        ) : (
          <SlotPicker slots={data} value={null} onChange={() => undefined} />
        )}
      </CardContent>
    </Card>
  );
}

function UpcomingCard({ userId }: { userId: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["booking", "upcoming"],
    queryFn: () => apiFetch<StaffBooking[]>("/booking/bookings?upcoming=true"),
  });
  const rows = (data ?? []).filter((b) => b.user.id === userId);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarCheck2 className="size-5" aria-hidden />
          جلسه‌های رزروشده پیش رو
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-24" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">هنوز مشتری‌ای زمانی رزرو نکرده است.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {rows.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <Link href={`/customers/${b.customer.id}`} className="font-medium hover:underline">
                    {b.customer.full_name}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {b.meeting_title} · {formatSlot(b.start_at, b.end_at)}
                  </p>
                </div>
                <CancelBookingDialog
                  staff
                  size="sm"
                  onCancel={async (reason) => {
                    await apiFetch(`/booking/bookings/${b.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
                    await queryClient.invalidateQueries({ queryKey: ["booking"] });
                    toast.success("جلسه لغو شد و به مشتری خبر داده شد.");
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
