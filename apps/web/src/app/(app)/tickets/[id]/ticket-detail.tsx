"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock, MessageSquare, Send, UserRoundCheck } from "lucide-react";
import { toast } from "sonner";

import { Field, InfoRow, Owner } from "@/components/crm/bits";
import { Breadcrumb, DetailError, DetailSkeleton } from "@/components/crm/detail-parts";
import { TICKET_STATUS_LABELS, TicketStatusBadge } from "@/components/crm/ticket-bits";
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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCode, formatDateTime } from "@/lib/format";
import type { TicketStatus } from "@/lib/portal";
import { useAssignableUsers } from "@/lib/queries";
import type { TicketDetail as Detail } from "@/lib/tickets";
import { cn } from "@/lib/utils";

export function TicketDetail({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const { data: ticket, error } = useQuery({
    queryKey: ["tickets", id],
    queryFn: () => apiFetch<Detail>(`/tickets/${id}`),
    refetchInterval: 30_000,
  });

  function accept(saved: Detail) {
    queryClient.setQueryData(["tickets", id], saved);
    void queryClient.invalidateQueries({ queryKey: ["tickets", "list"] });
    void queryClient.invalidateQueries({ queryKey: ["tickets", "count"] });
  }

  async function setStatus(status: TicketStatus) {
    try {
      accept(await apiFetch<Detail>(`/tickets/${id}/status`, { method: "POST", body: JSON.stringify({ status }) }));
      toast.success(status === "closed" ? "تیکت بسته شد و به مشتری خبر داده شد." : "وضعیت تغییر کرد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "انجام نشد.");
    }
  }

  if (error) return <DetailError error={error} />;
  if (!ticket) return <DetailSkeleton />;

  return (
    <>
      <Breadcrumb href="/tickets" label="تیکت‌ها" current={`شماره ${formatCode(ticket.number)}`} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{ticket.subject}</h1>
          <TicketStatusBadge status={ticket.status} />
        </div>
        <div className="flex flex-wrap gap-2">
          {ticket.status !== "closed" ? (
            <Button variant="outline" onClick={() => void setStatus("closed")}>
              بستن تیکت
            </Button>
          ) : (
            <Button variant="outline" onClick={() => void setStatus("in_progress")}>
              بازگشایی
            </Button>
          )}
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-4">
          <ol className="space-y-3" aria-label="گفت‌وگو و یادداشت‌ها">
            {ticket.messages.map((m) => (
              <li key={m.id} className={cn("flex", m.from_customer ? "justify-start" : "justify-end")}>
                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-7",
                    m.internal
                      ? "rounded-se-sm border border-dashed border-amber-300 bg-amber-50 text-amber-950"
                      : m.from_customer
                        ? "rounded-ss-sm bg-card ring-1 ring-border"
                        : "rounded-se-sm bg-accent text-accent-foreground",
                  )}
                >
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-medium opacity-80">
                    {m.internal ? <Lock className="size-3" aria-hidden /> : null}
                    {m.internal ? "یادداشت داخلی — " : m.from_customer ? "مشتری — " : ""}
                    {m.author} · {formatDateTime(m.created_at)}
                  </p>
                  <p className="whitespace-pre-wrap break-words">{m.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <ReplyBox ticket={ticket} onSaved={accept} />
        </div>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>جزئیات</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <InfoRow icon={<MessageSquare className="size-4" />} label="مشتری">
              <Link href={`/customers/${ticket.customer.id}`} className="text-primary hover:underline">
                {ticket.customer.full_name}
              </Link>
            </InfoRow>
            <InfoRow icon={<UserRoundCheck className="size-4" />} label="مسئول">
              {ticket.assignee ? <Owner user={ticket.assignee} /> : "بدون مسئول"}
            </InfoRow>
            <p className="pt-2 text-xs text-muted-foreground">
              شماره پیگیری {formatCode(ticket.number)} · {ticket.opened_by_customer ? "ثبت از پنل مشتری" : `ثبت توسط ${ticket.opened_by_user?.full_name ?? "کارکنان"}`} ·{" "}
              {formatDateTime(ticket.created_at)}
            </p>
            {ticket.can_manage ? <AssignDialog ticket={ticket} onSaved={accept} /> : null}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function ReplyBox({ ticket, onSaved }: { ticket: Detail; onSaved: (t: Detail) => void }) {
  const [internal, setInternal] = useState(false);
  const [body, setBody] = useState("");
  const [status, setStatus] = useState<TicketStatus | "">("");
  const [pending, setPending] = useState(false);

  async function send() {
    setPending(true);
    try {
      const saved = await apiFetch<Detail>(`/tickets/${ticket.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ body: body.trim(), internal, status: status || null }),
      });
      onSaved(saved);
      setBody("");
      setStatus("");
      toast.success(internal ? "یادداشت داخلی ثبت شد." : "پاسخ ارسال شد و به مشتری خبر داده شد.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ارسال انجام نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card className={cn(internal && "border-amber-300 bg-amber-50/40")}>
      <CardContent className="space-y-3">
        <div role="radiogroup" aria-label="نوع پیام" className="flex gap-1 rounded-lg border bg-card p-1 text-sm w-fit">
          {(
            [
              [false, "پاسخ به مشتری"],
              [true, "یادداشت داخلی"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={label}
              type="button"
              role="radio"
              aria-checked={internal === value}
              onClick={() => setInternal(value)}
              className={cn("rounded-md px-3 py-1.5", internal === value ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted")}
            >
              {label}
            </button>
          ))}
        </div>
        <Textarea
          aria-label={internal ? "یادداشت داخلی" : "پاسخ به مشتری"}
          rows={4}
          maxLength={5000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={internal ? "فقط کارکنان می‌بینند؛ برای مشتری نمایش داده نمی‌شود." : "مشتری این پاسخ را در پنل خود می‌بیند."}
        />
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="وضعیت پس از ارسال" htmlFor="reply-status">
            <NativeSelect id="reply-status" value={status} onChange={(e) => setStatus(e.target.value as TicketStatus | "")}>
              <NativeSelectOption value="">{internal ? "بدون تغییر" : "منتظر پاسخ مشتری (پیش‌فرض)"}</NativeSelectOption>
              {(Object.entries(TICKET_STATUS_LABELS) as [TicketStatus, string][]).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <Button onClick={() => void send()} disabled={pending || body.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : internal ? <Lock aria-hidden /> : <Send aria-hidden />}
            {internal ? "ثبت یادداشت" : "ارسال پاسخ"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function AssignDialog({ ticket, onSaved }: { ticket: Detail; onSaved: (t: Detail) => void }) {
  const { data: users = [] } = useAssignableUsers();
  const [open, setOpen] = useState(false);
  const [userId, setUserId] = useState(ticket.assignee?.id ?? "");
  const [pending, setPending] = useState(false);

  async function save() {
    setPending(true);
    try {
      onSaved(await apiFetch<Detail>(`/tickets/${ticket.id}/assign`, { method: "POST", body: JSON.stringify({ user_id: userId }) }));
      toast.success("تیکت واگذار شد.");
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "واگذاری انجام نشد.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant="outline" size="sm" className="mt-3 w-full">
            <UserRoundCheck aria-hidden />
            واگذاری
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>واگذاری تیکت شماره {formatCode(ticket.number)}</DialogTitle>
          <DialogDescription>به یکی از کاربران دامنه شما.</DialogDescription>
        </DialogHeader>
        <Field label="مسئول" htmlFor="assign-user">
          <NativeSelect id="assign-user" className="w-full" value={userId} onChange={(e) => setUserId(e.target.value)}>
            <NativeSelectOption value="">انتخاب کنید</NativeSelectOption>
            {users.map((u) => (
              <NativeSelectOption key={u.id} value={u.id}>
                {u.full_name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <DialogFooter>
          <Button onClick={() => void save()} disabled={pending || !userId || userId === ticket.assignee?.id}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            واگذاری
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
