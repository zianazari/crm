"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Mail, MessageSquareText, Send, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Badge } from "@/components/ui/badge";
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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, apiFetch } from "@/lib/api";
import { CHANNEL_LABELS, type Channel } from "@/lib/campaigns";
import { formatMobile, formatNumber, formatToman } from "@/lib/format";
import { keys, toQuery, type TimelineSubject } from "@/lib/queries";
import { cn } from "@/lib/utils";

export type MessageTemplate = {
  id: string;
  name: string;
  channel: Channel;
  kind: "service" | "marketing";
  subject: string | null;
  body: string;
  is_active: boolean;
  updated_at: string;
};

type Check = {
  allowed: boolean;
  reason: string | null;
  to: string | null;
  contact_name: string;
  subject: string | null;
  text: string;
  parts: number | null;
  cost: number;
  sent_today: number;
  daily_limit: number;
};

export const TEMPLATE_KIND_LABELS = { service: "اطلاع‌رسانی", marketing: "تبلیغاتی" } as const;

/** Sends one approved template from this record (spec section 5). The server checks the
 * address, consent, the do-not-send list, the window and the limits again on sending. */
export function SendMessageDialog({ subject }: { subject: TimelineSubject }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<Channel>("sms");
  const [templateId, setTemplateId] = useState("");
  const [requestId, setRequestId] = useState("");
  const [sending, setSending] = useState(false);

  const { data: templates } = useQuery({
    queryKey: ["message-templates", channel],
    queryFn: () => apiFetch<MessageTemplate[]>(`/message-templates${toQuery({ channel })}`),
    enabled: open,
  });
  const check = useQuery({
    queryKey: ["direct-messages", "check", templateId, subject],
    queryFn: () =>
      apiFetch<Check>("/direct-messages/check", {
        method: "POST",
        body: JSON.stringify({ template_id: templateId, ...subject }),
      }),
    enabled: open && Boolean(templateId),
  });
  const result = check.data;

  async function send() {
    setSending(true);
    try {
      await apiFetch("/direct-messages", {
        method: "POST",
        body: JSON.stringify({ template_id: templateId, request_id: requestId, ...subject }),
      });
      toast.success("پیام در صف ارسال قرار گرفت و در سابقه پرونده ثبت شد.");
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: keys.timeline });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ارسال انجام نشد.");
      void check.refetch();
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setTemplateId("");
          // One id per opening: a retried click returns the same send, never a second one.
          setRequestId(crypto.randomUUID());
        }
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <Send aria-hidden />
            ارسال پیام
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>ارسال پیام با قالب</DialogTitle>
          <DialogDescription>یکی از قالب‌های تأییدشده را انتخاب کنید؛ متن با اطلاعات همین پرونده تکمیل می‌شود.</DialogDescription>
        </DialogHeader>
        <div role="radiogroup" aria-label="کانال" className="grid grid-cols-2 gap-2">
          {(["sms", "email"] as const).map((c) => {
            const Icon = c === "sms" ? MessageSquareText : Mail;
            return (
              <button
                key={c}
                type="button"
                role="radio"
                aria-checked={channel === c}
                onClick={() => {
                  setChannel(c);
                  setTemplateId("");
                }}
                className={cn(
                  "flex items-center gap-2 rounded-lg border p-2.5 text-sm hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
                  channel === c && "border-primary bg-accent/60 font-medium ring-1 ring-primary",
                )}
              >
                <Icon className="size-4" aria-hidden />
                {CHANNEL_LABELS[c]}
              </button>
            );
          })}
        </div>
        <Field label="قالب" htmlFor="dm-template" required>
          <NativeSelect id="dm-template" className="w-full" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <NativeSelectOption value="">
              {!templates ? "در حال دریافت…" : templates.length ? "انتخاب قالب" : "قالبی برای این کانال تعریف نشده است"}
            </NativeSelectOption>
            {(templates ?? []).map((t) => (
              <NativeSelectOption key={t.id} value={t.id}>
                {t.name} ({TEMPLATE_KIND_LABELS[t.kind]})
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        {templateId ? (
          !result ? (
            <Skeleton className="h-32" />
          ) : (
            <div className="space-y-3" aria-live="polite">
              <p className="text-sm">
                به <span className="font-medium">{result.contact_name}</span>
                {result.to ? (
                  <bdi dir="ltr" className="ms-2 inline-block text-muted-foreground">
                    {channel === "sms" ? formatMobile(result.to) : result.to}
                  </bdi>
                ) : null}
              </p>
              {result.subject ? <p className="text-sm font-medium">موضوع: {result.subject}</p> : null}
              <p className="whitespace-pre-wrap break-words rounded-lg rounded-ss-none bg-accent px-3 py-2 text-[13px] leading-6 text-accent-foreground">
                {result.text.replace(/\/u\/0{48}$/, "/u/…")}
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                {result.parts ? <span>{formatNumber(result.parts)} بخش پیامک</span> : null}
                {result.cost ? <span>هزینه حدودی {formatToman(result.cost)}</span> : null}
                <span>
                  ارسال تکی امروز شما: {formatNumber(result.sent_today)} از {formatNumber(result.daily_limit)}
                </span>
              </div>
              {!result.allowed ? (
                <p role="alert" className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {result.reason}
                </p>
              ) : null}
            </div>
          )
        ) : null}
        <DialogFooter>
          <Button onClick={() => void send()} disabled={sending || !result?.allowed}>
            {sending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
            ارسال
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TemplateKindBadge({ kind }: { kind: MessageTemplate["kind"] }) {
  return (
    <Badge variant={kind === "marketing" ? "secondary" : "outline"} className={cn(kind === "marketing" && "bg-amber-100 text-amber-900")}>
      {TEMPLATE_KIND_LABELS[kind]}
    </Badge>
  );
}
