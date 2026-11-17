"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { AmountInput } from "@/components/crm/amount-input";
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
import { keys, useAssignableUsers, useStages } from "@/lib/queries";
import type { CustomerFull, DealFull } from "@/lib/types";

type Values = {
  title: string;
  customer: CustomerFull | null;
  organization_id: string;
  stage_id: string;
  amount: number | null;
  expected_close_date: string | null;
  owner_id: string;
  description: string;
};

export function DealFormDialog({
  deal,
  customer,
  stageId,
  trigger,
}: {
  deal?: DealFull;
  customer?: CustomerFull;
  stageId?: string;
  trigger: ReactElement;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: stages = [] } = useStages();
  const { data: assignable = [] } = useAssignableUsers();
  const editing = Boolean(deal);
  const initial = (): Values => ({
    title: deal?.title ?? "",
    customer: customer ?? null,
    organization_id: deal?.organization?.id ?? customer?.organizations[0]?.organization.id ?? "",
    stage_id: stageId ?? "",
    amount: deal?.amount ?? null,
    expected_close_date: deal?.expected_close_date ?? null,
    owner_id: "",
    description: deal?.description ?? "",
  });
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>(initial);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!editing && !values.customer) {
      setError("مشتری را انتخاب کنید.");
      return;
    }
    setPending(true);
    const common = {
      title: values.title,
      amount: values.amount,
      expected_close_date: values.expected_close_date,
      description: values.description || null,
      organization_id: values.organization_id || null,
    };
    try {
      const saved = editing
        ? await apiFetch<DealFull>(`/deals/${deal!.id}`, {
            method: "PATCH",
            body: JSON.stringify({ ...common, version: deal!.version }),
          })
        : await apiFetch<DealFull>("/deals", {
            method: "POST",
            body: JSON.stringify({
              ...common,
              customer_id: values.customer!.id,
              stage_id: values.stage_id || null,
              owner_id: values.owner_id || null,
            }),
          });
      await queryClient.invalidateQueries({ queryKey: keys.deals });
      setOpen(false);
      toast.success(editing ? "تغییرات ذخیره شد." : "فروش ثبت شد.");
      if (!editing) router.push(`/deals/${saved.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
      if (err instanceof ApiError && err.status === 409) {
        await queryClient.invalidateQueries({ queryKey: keys.deals });
      }
    } finally {
      setPending(false);
    }
  }

  const organizations = (editing ? null : values.customer)?.organizations ?? [];

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setValues(initial());
          setError(null);
        }
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{editing ? "ویرایش فروش" : "فروش جدید"}</DialogTitle>
          <DialogDescription>
            {editing ? "مرحله و نتیجه از تابلو یا پرونده فروش تغییر می‌کند." : "هر خرید یک فروش جداگانه است."}
          </DialogDescription>
        </DialogHeader>

        <form id="deal-form" onSubmit={(e) => void submit(e)} className="grid gap-4 sm:grid-cols-2">
          {!editing ? (
            <Field label="مشتری" required className="sm:col-span-2">
              {customer ? (
                <div className="flex h-9 items-center rounded-lg border bg-muted/40 px-3 text-sm">{customer.full_name}</div>
              ) : (
                <CustomerPicker
                  value={values.customer}
                  onChange={(c) => {
                    set("customer", c);
                    set("organization_id", c?.organizations[0]?.organization.id ?? "");
                  }}
                />
              )}
            </Field>
          ) : null}
          <Field label="عنوان فروش" htmlFor="deal-title" required className="sm:col-span-2">
            <Input
              id="deal-title"
              required
              minLength={2}
              value={values.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="مثلاً خرید لایسنس سالانه"
            />
          </Field>
          <Field label="مبلغ تخمینی" htmlFor="deal-amount">
            <AmountInput id="deal-amount" value={values.amount} onChange={(v) => set("amount", v)} />
          </Field>
          <Field label="تاریخ احتمالی بسته‌شدن" htmlFor="deal-close">
            <JalaliDateInput
              id="deal-close"
              value={values.expected_close_date}
              onChange={(v) => set("expected_close_date", v)}
            />
          </Field>
          {!editing ? (
            <Field label="مرحله" htmlFor="deal-stage">
              <NativeSelect
                id="deal-stage"
                value={values.stage_id}
                onChange={(e) => set("stage_id", e.target.value)}
                className="w-full"
              >
                <NativeSelectOption value="">مرحله اول</NativeSelectOption>
                {stages.map((s) => (
                  <NativeSelectOption key={s.id} value={s.id}>
                    {s.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          ) : null}
          {organizations.length ? (
            <Field label="به نمایندگی از سازمان" htmlFor="deal-org">
              <NativeSelect
                id="deal-org"
                value={values.organization_id}
                onChange={(e) => set("organization_id", e.target.value)}
                className="w-full"
              >
                <NativeSelectOption value="">خرید شخصی</NativeSelectOption>
                {organizations.map((o) => (
                  <NativeSelectOption key={o.organization.id} value={o.organization.id}>
                    {o.organization.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          ) : null}
          {!editing && assignable.length > 1 ? (
            <Field label="مسئول فروش" htmlFor="deal-owner" hint="خالی یعنی خودتان.">
              <NativeSelect
                id="deal-owner"
                value={values.owner_id}
                onChange={(e) => set("owner_id", e.target.value)}
                className="w-full"
              >
                <NativeSelectOption value="">خودم</NativeSelectOption>
                {assignable.map((u) => (
                  <NativeSelectOption key={u.id} value={u.id}>
                    {u.full_name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          ) : null}
          <Field label="توضیحات" htmlFor="deal-description" className="sm:col-span-2">
            <Textarea
              id="deal-description"
              rows={3}
              value={values.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </Field>
        </form>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button type="submit" form="deal-form" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {editing ? "ذخیره" : "ثبت فروش"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
