"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Check, Copy, Link2, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { CancelBookingDialog } from "@/components/booking/cancel-booking-dialog";
import { formatSlot } from "@/components/booking/slot-picker";
import { Field } from "@/components/crm/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ApiError, apiFetch } from "@/lib/api";
import {
  type BookingLink,
  type BookingSettings,
  type Channel,
  type StaffBooking,
} from "@/lib/booking";
import { formatDate, formatMobile, formatNumber } from "@/lib/format";
import { canManage, toQuery, useAssignableUsers, useDeals, useMe } from "@/lib/queries";
import type { CustomerFull } from "@/lib/types";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

const STATUS: Record<StaffBooking["status"], string> = {
  confirmed: "قطعی",
  canceled: "لغوشده",
  rescheduled: "جابه‌جاشده",
};

/** Booking links and booked meetings on a customer's record (spec 4.10). */
export function CustomerBooking({ customer, editable }: { customer: CustomerFull; editable: boolean }) {
  const queryClient = useQueryClient();
  const bookings = useQuery({
    queryKey: ["booking", "customer", customer.id, "bookings"],
    queryFn: async () => ({
      rows: await apiFetch<StaffBooking[]>(`/booking/bookings?customer_id=${customer.id}`),
      now: Date.now(),
    }),
  });
  const links = useQuery({
    queryKey: ["booking", "customer", customer.id, "links"],
    queryFn: () => apiFetch<BookingLink[]>(`/booking/links?customer_id=${customer.id}`),
  });
  const rows = bookings.data?.rows ?? [];
  const now = bookings.data?.now ?? 0;
  const upcoming = rows.filter((b) => b.status === "confirmed" && new Date(b.end_at).getTime() > now);
  const past = rows.filter((b) => !upcoming.includes(b)).slice(0, 5);
  const openLinks = (links.data ?? []).filter((l) => l.state === "open");

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["booking"] });
    await queryClient.invalidateQueries({ queryKey: ["activities"] });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="size-5" aria-hidden />
          رزرو جلسه
        </CardTitle>
        {editable ? <SendLinkDialog customer={customer} onCreated={() => void refresh()} /> : null}
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {upcoming.length === 0 && openLinks.length === 0 && past.length === 0 ? (
          <p className="text-muted-foreground">
            با «ارسال لینک زمان‌های آزاد» مشتری خودش از تقویم شما یک زمان انتخاب می‌کند و جلسه در فعالیت‌ها ثبت می‌شود.
          </p>
        ) : null}
        {upcoming.length > 0 ? (
          <ul className="space-y-2">
            {upcoming.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-emerald-200 bg-emerald-50/50 px-3 py-2">
                <div>
                  <p className="font-medium">{formatSlot(b.start_at, b.end_at)}</p>
                  <p className="text-xs text-muted-foreground">
                    {b.meeting_title} · با {b.user.full_name}
                  </p>
                </div>
                {editable ? (
                  <CancelBookingDialog
                    staff
                    size="sm"
                    onCancel={async (reason) => {
                      await apiFetch(`/booking/bookings/${b.id}/cancel`, { method: "POST", body: JSON.stringify({ reason }) });
                      await refresh();
                      toast.success("جلسه لغو شد و به مشتری خبر داده شد.");
                    }}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {openLinks.length > 0 ? (
          <div className="space-y-2">
            <p className="font-medium">لینک‌های منتظر انتخاب زمان</p>
            <ul className="space-y-2">
              {openLinks.map((l) => (
                <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2">
                  <span>
                    {l.meeting_type.title} · {l.user.full_name}
                    <span className="block text-xs text-muted-foreground">
                      {l.sent_via ? (l.sent_via === "sms" ? "پیامک شد" : "ایمیل شد") : "کپی شد"} · تا {formatDate(l.expires_at)} معتبر
                    </span>
                  </span>
                  {editable ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      onClick={async () => {
                        try {
                          await apiFetch(`/booking/links/${l.id}/revoke`, { method: "POST" });
                          await refresh();
                          toast.success("لینک باطل شد.");
                        } catch (err) {
                          toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
                        }
                      }}
                    >
                      ابطال
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {past.length > 0 ? (
          <div className="space-y-1 border-t pt-3">
            <p className="font-medium">سابقه</p>
            <ul className="space-y-1 text-muted-foreground">
              {past.map((b) => (
                <li key={b.id} className="flex flex-wrap justify-between gap-2">
                  <span>
                    {b.meeting_title} · {formatSlot(b.start_at)}
                  </span>
                  <span className={cn("text-xs", b.status === "canceled" && "text-destructive")}>
                    {b.status === "canceled" ? `لغو توسط ${b.canceled_by ? b.canceled_by.full_name : "مشتری"}` : STATUS[b.status]}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SendLinkDialog({ customer, onCreated }: { customer: CustomerFull; onCreated: () => void }) {
  const { data: me } = useMe();
  const hydrated = useHydrated();
  const manager = hydrated && canManage(me?.role);
  const { data: users = [] } = useAssignableUsers();
  const { data: deals } = useDeals({ customer_id: customer.id, status: "open", page_size: 50 });
  const [open, setOpen] = useState(false);
  const [owner, setOwner] = useState<string>("");
  const [typeId, setTypeId] = useState("");
  const [dealId, setDealId] = useState("");
  const [days, setDays] = useState(14);
  const [send, setSend] = useState<Channel | "">(customer.mobile ? "sms" : customer.email ? "email" : "");
  const [pending, setPending] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const settings = useQuery({
    queryKey: ["booking", "settings", owner || "me"],
    queryFn: () => apiFetch<BookingSettings>(`/booking/settings${toQuery({ user_id: owner || null })}`),
    enabled: open,
  });
  const types = (settings.data?.meeting_types ?? []).filter((t) => t.is_active);
  const chosenType = typeId && types.some((t) => t.id === typeId) ? typeId : (types[0]?.id ?? "");
  const openDeals = (deals?.items ?? []).filter((d) => d.access === "full");

  async function create() {
    setPending(true);
    try {
      const created = await apiFetch<{ url: string }>("/booking/links", {
        method: "POST",
        body: JSON.stringify({
          customer_id: customer.id,
          meeting_type_id: chosenType,
          deal_id: dealId || null,
          expires_in_days: days,
          send: send || null,
        }),
      });
      setUrl(created.url);
      onCreated();
      toast.success(send ? "لینک برای مشتری فرستاده شد." : "لینک ساخته شد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ساخته نشد.");
    } finally {
      setPending(false);
    }
  }

  async function copy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      toast.error("کپی نشد؛ نشانی را دستی انتخاب کنید.");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setOwner("");
          setTypeId("");
          setDealId("");
          setDays(14);
          setSend(customer.mobile ? "sms" : customer.email ? "email" : "");
          setUrl(null);
          setCopied(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <Send aria-hidden />
            ارسال لینک زمان‌های آزاد
          </Button>
        }
      />
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>ارسال لینک زمان‌های آزاد</DialogTitle>
          <DialogDescription>
            {customer.full_name} فقط زمان‌های آزاد این تقویم را می‌بیند و پیش از رزرو با کد یک‌بارمصرف تأیید می‌شود.
          </DialogDescription>
        </DialogHeader>
        {url ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-sm font-medium text-emerald-700">
              <Check className="size-4" aria-hidden />
              لینک آماده است{send ? ` و ${send === "sms" ? "پیامک" : "ایمیل"} آن در صف ارسال است` : ""}.
            </p>
            <div className="flex gap-2">
              <Input readOnly dir="ltr" value={url} aria-label="نشانی لینک" onFocus={(e) => e.target.select()} />
              <Button variant="outline" onClick={() => void copy()}>
                {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                {copied ? "کپی شد" : "کپی"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">این نشانی فقط همین یک‌بار نمایش داده می‌شود؛ اگر گم شد، لینک تازه بسازید.</p>
          </div>
        ) : (
          <>
            {manager && users.length > 1 ? (
              <Field label="تقویم چه کسی" htmlFor="bl-owner">
                <NativeSelect id="bl-owner" className="w-full" value={owner} onChange={(e) => { setOwner(e.target.value); setTypeId(""); }}>
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
            ) : null}
            <Field label="نوع جلسه" htmlFor="bl-type" required>
              <NativeSelect id="bl-type" className="w-full" value={chosenType} onChange={(e) => setTypeId(e.target.value)} disabled={!settings.data}>
                {types.length === 0 ? <NativeSelectOption value="">نوع جلسه فعالی نیست</NativeSelectOption> : null}
                {types.map((t) => (
                  <NativeSelectOption key={t.id} value={t.id}>
                    {t.title} — {formatNumber(t.duration_minutes)} دقیقه
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            {openDeals.length > 0 ? (
              <Field label="فروش مرتبط" htmlFor="bl-deal" hint="جلسه به این فروش هم متصل می‌شود.">
                <NativeSelect id="bl-deal" className="w-full" value={dealId} onChange={(e) => setDealId(e.target.value)}>
                  <NativeSelectOption value="">بدون فروش</NativeSelectOption>
                  {openDeals.map((d) => (
                    <NativeSelectOption key={d.id} value={d.id}>
                      {d.title}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
            ) : null}
            <Field label="اعتبار لینک" htmlFor="bl-days">
              <NativeSelect id="bl-days" className="w-full" value={String(days)} onChange={(e) => setDays(Number(e.target.value))}>
                {[3, 7, 14, 30, 60].map((d) => (
                  <NativeSelectOption key={d} value={String(d)}>
                    {formatNumber(d)} روز
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">ارسال</legend>
              {(
                [
                  ["sms", customer.mobile ? `پیامک به ${formatMobile(customer.mobile)}` : null],
                  ["email", customer.email ? `ایمیل به ${customer.email}` : null],
                  ["", "فقط ساخت لینک (کپی می‌کنم)"],
                ] as const
              )
                .filter(([, label]) => label)
                .map(([value, label]) => (
                  <label key={value || "copy"} className="flex items-center gap-2 text-sm">
                    <input type="radio" name="bl-send" className="size-4 accent-primary" checked={send === value} onChange={() => setSend(value)} />
                    <bdi>{label}</bdi>
                  </label>
                ))}
            </fieldset>
          </>
        )}
        <DialogFooter>
          {url ? (
            <Button variant="outline" onClick={() => setOpen(false)}>
              بستن
            </Button>
          ) : (
            <Button onClick={() => void create()} disabled={pending || !chosenType}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Link2 aria-hidden />}
              {send ? "ساخت و ارسال" : "ساخت لینک"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
