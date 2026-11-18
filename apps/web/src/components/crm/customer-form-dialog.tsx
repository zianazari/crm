"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DuplicateAlert } from "@/components/crm/duplicate-alert";
import { Field } from "@/components/crm/bits";
import { OrganizationPicker } from "@/components/crm/organization-picker";
import { TagPicker } from "@/components/crm/tag-picker";
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
import { ConsentFields } from "@/components/crm/consent-fields";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch, duplicateMatches } from "@/lib/api";
import { formatMobile } from "@/lib/format";
import { keys, useAssignableUsers, useSources } from "@/lib/queries";
import { CHANNEL_LABELS, type ContactChannel, type CustomerFull, type DuplicateMatch, type Ref } from "@/lib/types";

type Values = {
  full_name: string;
  mobile: string;
  phone: string;
  email: string;
  preferred_channel: ContactChannel | "";
  source_id: string;
  owner_id: string;
  organization: Ref | null;
  job_title: string;
  description: string;
  tag_ids: string[];
  sms_consent: boolean;
  email_consent: boolean;
};

function initialValues(customer?: CustomerFull): Values {
  return {
    full_name: customer?.full_name ?? "",
    mobile: customer?.mobile ? formatMobile(customer.mobile) : "",
    phone: customer?.phone ?? "",
    email: customer?.email ?? "",
    preferred_channel: customer?.preferred_channel ?? "",
    source_id: customer?.source?.id ?? "",
    owner_id: "",
    organization: null,
    job_title: "",
    description: customer?.description ?? "",
    tag_ids: customer?.tags.map((t) => t.id) ?? [],
    sms_consent: customer?.sms_consent ?? false,
    email_consent: customer?.email_consent ?? false,
  };
}

export function CustomerFormDialog({ customer, trigger }: { customer?: CustomerFull; trigger: ReactElement }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: sources = [] } = useSources();
  const { data: assignable = [] } = useAssignableUsers();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>(() => initialValues(customer));
  const [duplicates, setDuplicates] = useState<DuplicateMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const editing = Boolean(customer);

  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  function reset(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) {
      setValues(initialValues(customer));
      setDuplicates(null);
      setError(null);
    }
  }

  async function submit(event: FormEvent, allowDuplicate = false) {
    event.preventDefault();
    setError(null);
    if (!values.mobile.trim() && !values.email.trim() && !values.phone.trim()) {
      setError("حداقل یکی از موبایل، تلفن یا ایمیل را وارد کنید.");
      return;
    }
    setPending(true);
    const body = {
      full_name: values.full_name,
      mobile: values.mobile || null,
      phone: values.phone || null,
      email: values.email || null,
      preferred_channel: values.preferred_channel || null,
      source_id: values.source_id || null,
      description: values.description || null,
      tag_ids: values.tag_ids,
      sms_consent: values.sms_consent,
      email_consent: values.email_consent,
      ...(editing
        ? {}
        : {
            owner_id: values.owner_id || null,
            organization_id: values.organization?.id ?? null,
            job_title: values.job_title || null,
            allow_duplicate: allowDuplicate,
          }),
    };
    try {
      const saved = editing
        ? await apiFetch<CustomerFull>(
            `/customers/${customer!.id}${allowDuplicate ? "?allow_duplicate=true" : ""}`,
            { method: "PATCH", body: JSON.stringify(body) },
          )
        : await apiFetch<CustomerFull>("/customers", { method: "POST", body: JSON.stringify(body) });
      await queryClient.invalidateQueries({ queryKey: keys.customers });
      setOpen(false);
      toast.success(editing ? "تغییرات ذخیره شد." : "مشتری ثبت شد.");
      if (!editing) router.push(`/customers/${saved.id}`);
    } catch (err) {
      const matches = duplicateMatches(err);
      if (matches) setDuplicates(matches);
      else setError(err instanceof ApiError ? err.message : "خطایی رخ داد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger render={trigger} />
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{editing ? "ویرایش مشتری" : "مشتری جدید"}</DialogTitle>
          <DialogDescription>حداقل یکی از موبایل، تلفن یا ایمیل لازم است.</DialogDescription>
        </DialogHeader>

        <form id="customer-form" onSubmit={(e) => void submit(e)} className="grid gap-4 sm:grid-cols-2">
          <Field label="نام و نام خانوادگی" htmlFor="c-name" required className="sm:col-span-2">
            <Input
              id="c-name"
              required
              minLength={2}
              value={values.full_name}
              onChange={(e) => set("full_name", e.target.value)}
            />
          </Field>
          <Field label="موبایل" htmlFor="c-mobile">
            <Input
              id="c-mobile"
              dir="ltr"
              type="tel"
              inputMode="tel"
              placeholder="09xxxxxxxxx"
              value={values.mobile}
              onChange={(e) => {
                set("mobile", e.target.value);
                setDuplicates(null);
              }}
              className="text-start"
            />
          </Field>
          <Field label="تلفن ثابت" htmlFor="c-phone">
            <Input
              id="c-phone"
              dir="ltr"
              type="tel"
              value={values.phone}
              onChange={(e) => set("phone", e.target.value)}
              className="text-start"
            />
          </Field>
          <Field label="ایمیل" htmlFor="c-email">
            <Input
              id="c-email"
              dir="ltr"
              type="email"
              value={values.email}
              onChange={(e) => {
                set("email", e.target.value);
                setDuplicates(null);
              }}
              className="text-start"
            />
          </Field>
          <Field label="کانال ترجیحی ارتباط" htmlFor="c-channel">
            <NativeSelect
              id="c-channel"
              value={values.preferred_channel}
              onChange={(e) => set("preferred_channel", e.target.value as ContactChannel | "")}
              className="w-full"
            >
              <NativeSelectOption value="">مشخص نشده</NativeSelectOption>
              {(Object.keys(CHANNEL_LABELS) as ContactChannel[]).map((c) => (
                <NativeSelectOption key={c} value={c}>
                  {CHANNEL_LABELS[c]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Field label="منبع جذب" htmlFor="c-source">
            <NativeSelect
              id="c-source"
              value={values.source_id}
              onChange={(e) => set("source_id", e.target.value)}
              className="w-full"
            >
              <NativeSelectOption value="">انتخاب نشده</NativeSelectOption>
              {sources.map((s) => (
                <NativeSelectOption key={s.id} value={s.id}>
                  {s.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          {!editing && assignable.length > 1 ? (
            <Field label="مسئول" htmlFor="c-owner" hint="خالی یعنی خودتان.">
              <NativeSelect
                id="c-owner"
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
          {!editing ? (
            <>
              <Field label="سازمان" hint="اگر نماینده سازمانی است." className="sm:col-span-2">
                <OrganizationPicker value={values.organization} onChange={(o) => set("organization", o)} />
              </Field>
              {values.organization ? (
                <Field label="سمت در سازمان" htmlFor="c-job" className="sm:col-span-2">
                  <Input id="c-job" value={values.job_title} onChange={(e) => set("job_title", e.target.value)} />
                </Field>
              ) : null}
            </>
          ) : null}
          <Field label="برچسب‌ها" className="sm:col-span-2">
            <TagPicker value={values.tag_ids} onChange={(ids) => set("tag_ids", ids)} />
          </Field>
          <ConsentFields
            idPrefix="c"
            sms={values.sms_consent}
            email={values.email_consent}
            onChange={(next) => setValues((v) => ({ ...v, sms_consent: next.sms, email_consent: next.email }))}
          />
          <Field label="توضیحات" htmlFor="c-description" className="sm:col-span-2">
            <Textarea
              id="c-description"
              rows={3}
              value={values.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </Field>
        </form>

        {duplicates ? <DuplicateAlert matches={duplicates} /> : null}
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          {duplicates ? (
            <Button variant="outline" disabled={pending} onClick={(e) => void submit(e, true)}>
              ثبت با وجود تکرار
            </Button>
          ) : null}
          <Button type="submit" form="customer-form" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {editing ? "ذخیره" : "ثبت"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
