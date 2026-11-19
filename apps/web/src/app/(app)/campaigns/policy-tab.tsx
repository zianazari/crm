"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { AmountInput } from "@/components/crm/amount-input";
import { Field } from "@/components/crm/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import type { Policy } from "@/lib/campaigns";
import { formatNumber, formatToman, toAsciiDigits } from "@/lib/format";

const KEY = ["campaigns", "policy"] as const;

function int(value: string): number {
  const n = Number.parseInt(toAsciiDigits(value), 10);
  return Number.isFinite(n) ? n : 0;
}

/** Sending rules for marketing (spec 4.5): set by an admin, visible to managers. */
export function PolicyTab({ admin }: { admin: boolean }) {
  const { data } = useQuery({ queryKey: KEY, queryFn: () => apiFetch<Policy>("/campaigns/policy") });
  if (!data) return <Skeleton className="h-80" />;
  return <PolicyForm admin={admin} data={data} />;
}

function PolicyForm({ admin, data }: { admin: boolean; data: Policy }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Policy>(data);
  const [pending, setPending] = useState(false);
  const set = (patch: Partial<Policy>) => setValues({ ...values, ...patch });

  async function save() {
    setPending(true);
    try {
      const saved = await apiFetch<Policy>("/campaigns/policy", {
        method: "PUT",
        body: JSON.stringify({
          window_start: values.window_start.slice(0, 5),
          window_end: values.window_end.slice(0, 5),
          sms_daily_limit: values.sms_daily_limit,
          email_daily_limit: values.email_daily_limit,
          sms_unit_price: values.sms_unit_price,
          email_unit_price: values.email_unit_price,
          monthly_budget: values.monthly_budget,
          user_daily_limit: values.user_daily_limit,
        }),
      });
      queryClient.setQueryData(KEY, saved);
      toast.success("قواعد ارسال ذخیره شد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ذخیره انجام نشد. ساعت شروع باید پیش از ساعت پایان باشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-6">
        {!admin ? (
          <p className="text-sm text-muted-foreground">این قواعد را ادمین تعیین می‌کند؛ کمپین‌ها در همین محدوده ارسال می‌شوند.</p>
        ) : null}
        <fieldset disabled={!admin} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="شروع ساعت مجاز ارسال" htmlFor="p-start" hint="به وقت تهران.">
            <Input id="p-start" type="time" dir="ltr" value={values.window_start.slice(0, 5)} onChange={(e) => set({ window_start: e.target.value })} />
          </Field>
          <Field label="پایان ساعت مجاز ارسال" htmlFor="p-end">
            <Input id="p-end" type="time" dir="ltr" value={values.window_end.slice(0, 5)} onChange={(e) => set({ window_end: e.target.value })} />
          </Field>
          <div className="hidden lg:block" />
          <Field label="سقف روزانه پیامک تبلیغاتی" htmlFor="p-sms-limit">
            <Input id="p-sms-limit" inputMode="numeric" value={formatNumber(values.sms_daily_limit)} onChange={(e) => set({ sms_daily_limit: int(e.target.value) })} />
          </Field>
          <Field label="سقف روزانه ایمیل تبلیغاتی" htmlFor="p-email-limit">
            <Input id="p-email-limit" inputMode="numeric" value={formatNumber(values.email_daily_limit)} onChange={(e) => set({ email_daily_limit: int(e.target.value) })} />
          </Field>
          <div className="hidden lg:block" />
          <Field label="قیمت هر بخش پیامک (تومان)" htmlFor="p-sms-price" hint="برای برآورد هزینه، تا انتخاب سرویس‌دهنده.">
            <AmountInput id="p-sms-price" value={values.sms_unit_price} onChange={(v) => set({ sms_unit_price: v ?? 0 })} />
          </Field>
          <Field label="قیمت هر ایمیل (تومان)" htmlFor="p-email-price">
            <AmountInput id="p-email-price" value={values.email_unit_price} onChange={(v) => set({ email_unit_price: v ?? 0 })} />
          </Field>
          <Field label="سقف ارسال تکی هر نفر در روز" htmlFor="p-user-limit" hint="پیام‌هایی که کارشناس با قالب از پرونده می‌فرستد.">
            <Input id="p-user-limit" inputMode="numeric" value={formatNumber(values.user_daily_limit)} onChange={(e) => set({ user_daily_limit: int(e.target.value) })} />
          </Field>
          <Field label="سقف مصرف ۳۰ روز اخیر (تومان)" htmlFor="p-budget" hint="خالی یعنی بدون سقف؛ با رسیدن به سقف، کمپین متوقف می‌شود.">
            <AmountInput id="p-budget" value={values.monthly_budget} onChange={(v) => set({ monthly_budget: v })} />
          </Field>
        </fieldset>
        <p className="text-sm text-muted-foreground">
          مصرف ۳۰ روز اخیر: <span className="font-medium text-foreground">{formatToman(data.spent_30_days)}</span>
        </p>
        {admin ? (
          <Button onClick={() => void save()} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره قواعد
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
