"use client";

import { useState, type ReactElement } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Pencil, Plus } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { TEMPLATE_KIND_LABELS, TemplateKindBadge, type MessageTemplate } from "@/components/crm/send-message-dialog";
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
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { CHANNEL_LABELS, type Channel } from "@/lib/campaigns";
import { cn } from "@/lib/utils";

const KEY = ["message-templates"] as const;

/** Approved texts that staff send one at a time from a record (spec section 5). */
export function TemplatesTab() {
  const { data, isPending } = useQuery({
    queryKey: [...KEY, "all"],
    queryFn: () => apiFetch<MessageTemplate[]>("/message-templates?include_inactive=true"),
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          کارشناسان از داخل پرونده خود فقط همین قالب‌ها را می‌فرستند، با سقف روزانه هر نفر. قالب «تبلیغاتی» فقط به مخاطب دارای
          اجازه و در ساعت مجاز می‌رود و پیوند لغو دارد؛ «اطلاع‌رسانی» برای امور خود مشتری است، مثل فاکتور یا قرار ملاقات.
        </p>
        <TemplateDialog trigger={<Button><Plus aria-hidden />قالب جدید</Button>} />
      </div>
      {isPending || !data ? (
        <Skeleton className="h-40" />
      ) : data.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">هنوز قالبی تعریف نشده است.</CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((t) => (
            <Card key={t.id} className={cn(!t.is_active && "opacity-60")}>
              <CardContent className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">{t.name}</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <Badge variant="outline">{CHANNEL_LABELS[t.channel]}</Badge>
                      <TemplateKindBadge kind={t.kind} />
                      {!t.is_active ? <Badge variant="outline">غیرفعال</Badge> : null}
                    </div>
                  </div>
                  <TemplateDialog
                    template={t}
                    trigger={<Button variant="ghost" size="icon-sm" aria-label={`ویرایش ${t.name}`}><Pencil /></Button>}
                  />
                </div>
                {t.subject ? <p className="text-xs font-medium">موضوع: {t.subject}</p> : null}
                <p className="line-clamp-4 whitespace-pre-wrap text-sm text-muted-foreground">{t.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function TemplateDialog({ template, trigger }: { template?: MessageTemplate; trigger: ReactElement }) {
  const queryClient = useQueryClient();
  const initial = {
    name: template?.name ?? "",
    channel: template?.channel ?? ("sms" as Channel),
    kind: template?.kind ?? ("service" as MessageTemplate["kind"]),
    subject: template?.subject ?? "",
    body: template?.body ?? "",
    is_active: template?.is_active ?? true,
  };
  const [open, setOpen] = useState(false);
  const [v, setV] = useState(initial);
  const [pending, setPending] = useState(false);
  const set = (patch: Partial<typeof initial>) => setV((x) => ({ ...x, ...patch }));

  async function save() {
    setPending(true);
    try {
      await apiFetch(template ? `/message-templates/${template.id}` : "/message-templates", {
        method: template ? "PUT" : "POST",
        body: JSON.stringify({ ...v, subject: v.channel === "email" ? v.subject : null }),
      });
      toast.success("قالب ذخیره شد.");
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: KEY });
    } catch (err) {
      toast.error(
        err instanceof ApiError && err.status !== 422 ? err.message : "قالب کامل نیست؛ ایمیل موضوع لازم دارد و متن پیامک حداکثر ۱۰۰۰ نویسه است.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setV(initial);
      }}
    >
      <DialogTrigger render={trigger} />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{template ? "ویرایش قالب" : "قالب جدید"}</DialogTitle>
          <DialogDescription>{"{name}"} نام مخاطب، {"{owner}"} نام فرستنده و {"{deal}"} عنوان فروش را جایگزین می‌کند.</DialogDescription>
        </DialogHeader>
        <Field label="نام قالب" htmlFor="tpl-name" required>
          <Input id="tpl-name" maxLength={120} value={v.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="کانال" htmlFor="tpl-channel">
            <NativeSelect id="tpl-channel" className="w-full" value={v.channel} onChange={(e) => set({ channel: e.target.value as Channel })}>
              <NativeSelectOption value="sms">پیامک</NativeSelectOption>
              <NativeSelectOption value="email">ایمیل</NativeSelectOption>
            </NativeSelect>
          </Field>
          <Field label="نوع" htmlFor="tpl-kind">
            <NativeSelect id="tpl-kind" className="w-full" value={v.kind} onChange={(e) => set({ kind: e.target.value as MessageTemplate["kind"] })}>
              {Object.entries(TEMPLATE_KIND_LABELS).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
        </div>
        {v.channel === "email" ? (
          <Field label="موضوع" htmlFor="tpl-subject" required>
            <Input id="tpl-subject" maxLength={200} value={v.subject} onChange={(e) => set({ subject: e.target.value })} />
          </Field>
        ) : null}
        <Field label="متن" htmlFor="tpl-body" required>
          <Textarea id="tpl-body" rows={5} value={v.body} onChange={(e) => set({ body: e.target.value })} />
        </Field>
        {template ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={v.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
            قالب فعال است
          </label>
        ) : null}
        <DialogFooter>
          <Button onClick={() => void save()} disabled={pending || v.name.trim().length < 2 || v.body.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ذخیره
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
