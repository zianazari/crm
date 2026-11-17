"use client";

import { useState, type FormEvent, type ReactElement } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { DuplicateAlert } from "@/components/crm/duplicate-alert";
import { Field } from "@/components/crm/bits";
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
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch, duplicateMatches } from "@/lib/api";
import { formatMobile } from "@/lib/format";
import { keys, useAssignableUsers, useSources } from "@/lib/queries";
import type { DuplicateMatch, LeadFull } from "@/lib/types";

type Values = {
  full_name: string;
  mobile: string;
  email: string;
  company_name: string;
  source_id: string;
  owner_id: string;
  description: string;
  tag_ids: string[];
};

function initialValues(lead?: LeadFull): Values {
  return {
    full_name: lead?.full_name ?? "",
    mobile: lead?.mobile ? formatMobile(lead.mobile) : "",
    email: lead?.email ?? "",
    company_name: lead?.company_name ?? "",
    source_id: lead?.source?.id ?? "",
    owner_id: "",
    description: lead?.description ?? "",
    tag_ids: lead?.tags.map((t) => t.id) ?? [],
  };
}

export function LeadFormDialog({ lead, trigger }: { lead?: LeadFull; trigger: ReactElement }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: sources = [] } = useSources();
  const { data: assignable = [] } = useAssignableUsers();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>(() => initialValues(lead));
  const [duplicates, setDuplicates] = useState<DuplicateMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const editing = Boolean(lead);

  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  function reset(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) {
      setValues(initialValues(lead));
      setDuplicates(null);
      setError(null);
    }
  }

  async function submit(event: FormEvent, allowDuplicate = false) {
    event.preventDefault();
    setError(null);
    if (!values.mobile.trim() && !values.email.trim()) {
      setError("موبایل یا ایمیل را وارد کنید.");
      return;
    }
    setPending(true);
    const body = {
      full_name: values.full_name,
      mobile: values.mobile || null,
      email: values.email || null,
      company_name: values.company_name || null,
      source_id: values.source_id || null,
      description: values.description || null,
      tag_ids: values.tag_ids,
      ...(editing ? {} : { owner_id: values.owner_id || null, allow_duplicate: allowDuplicate }),
    };
    try {
      const saved = editing
        ? await apiFetch<LeadFull>(`/leads/${lead!.id}${allowDuplicate ? "?allow_duplicate=true" : ""}`, {
            method: "PATCH",
            body: JSON.stringify(body),
          })
        : await apiFetch<LeadFull>("/leads", { method: "POST", body: JSON.stringify(body) });
      await queryClient.invalidateQueries({ queryKey: keys.leads });
      setOpen(false);
      toast.success(editing ? "تغییرات ذخیره شد." : "مشتری احتمالی ثبت شد.");
      if (!editing) router.push(`/leads/${saved.id}`);
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
          <DialogTitle>{editing ? "ویرایش مشتری احتمالی" : "مشتری احتمالی جدید"}</DialogTitle>
          <DialogDescription>حداقل یکی از موبایل یا ایمیل لازم است.</DialogDescription>
        </DialogHeader>

        <form id="lead-form" onSubmit={(e) => void submit(e)} className="grid gap-4 sm:grid-cols-2">
          <Field label="نام و نام خانوادگی" htmlFor="lead-name" required className="sm:col-span-2">
            <Input
              id="lead-name"
              required
              minLength={2}
              value={values.full_name}
              onChange={(e) => set("full_name", e.target.value)}
            />
          </Field>
          <Field label="موبایل" htmlFor="lead-mobile">
            <Input
              id="lead-mobile"
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
          <Field label="ایمیل" htmlFor="lead-email">
            <Input
              id="lead-email"
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
          <Field label="شرکت" htmlFor="lead-company">
            <Input
              id="lead-company"
              value={values.company_name}
              onChange={(e) => set("company_name", e.target.value)}
            />
          </Field>
          <Field label="منبع جذب" htmlFor="lead-source">
            <NativeSelect
              id="lead-source"
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
            <Field label="مسئول" htmlFor="lead-owner" hint="خالی یعنی خودتان.">
              <NativeSelect
                id="lead-owner"
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
          <Field label="برچسب‌ها" className="sm:col-span-2">
            <TagPicker value={values.tag_ids} onChange={(ids) => set("tag_ids", ids)} />
          </Field>
          <Field label="توضیحات" htmlFor="lead-description" className="sm:col-span-2">
            <Textarea
              id="lead-description"
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
          <Button type="submit" form="lead-form" disabled={pending}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {editing ? "ذخیره" : "ثبت"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
