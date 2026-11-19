"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { TicketStatusBadge } from "@/components/crm/ticket-bits";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { formatCode, formatDateTime } from "@/lib/format";
import { portalFetch, type PortalTicketDetail } from "@/lib/portal";
import { cn } from "@/lib/utils";

export function PortalTicketView({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const { data: ticket, error } = useQuery({
    queryKey: ["portal", "ticket", id],
    queryFn: () => portalFetch<PortalTicketDetail>(`/tickets/${id}`),
    refetchInterval: 30_000,
  });
  const [reply, setReply] = useState("");
  const [pending, setPending] = useState(false);

  async function send() {
    setPending(true);
    try {
      const saved = await portalFetch<PortalTicketDetail>(`/tickets/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ body: reply.trim() }),
      });
      queryClient.setQueryData(["portal", "ticket", id], saved);
      void queryClient.invalidateQueries({ queryKey: ["portal", "tickets"] });
      setReply("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ارسال انجام نشد.");
    } finally {
      setPending(false);
    }
  }

  if (error) {
    return (
      <Alert>
        <AlertTitle>درخواست پیدا نشد</AlertTitle>
        <AlertDescription>
          <Link href="/portal" className="text-primary hover:underline">
            بازگشت به درخواست‌های من
          </Link>
        </AlertDescription>
      </Alert>
    );
  }
  if (!ticket) return <Skeleton className="h-96" />;

  return (
    <>
      <div className="space-y-2">
        <Link href="/portal" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ChevronRight className="size-4" aria-hidden />
          درخواست‌های من
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-bold">{ticket.subject}</h1>
          <TicketStatusBadge status={ticket.status} label={ticket.status_label} />
        </div>
        <p className="text-xs text-muted-foreground">
          شماره پیگیری {formatCode(ticket.number)} · ثبت {formatDateTime(ticket.created_at)}
        </p>
      </div>
      <ol className="space-y-3" aria-label="گفت‌وگو">
        {ticket.messages.map((m) => (
          <li key={m.id} className={cn("flex", m.from_me ? "justify-start" : "justify-end")}>
            <div
              className={cn(
                "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-7",
                m.from_me ? "rounded-ss-sm bg-card ring-1 ring-border" : "rounded-se-sm bg-accent text-accent-foreground",
              )}
            >
              <p className="mb-1 text-xs font-medium opacity-80">
                {m.from_me ? "شما" : `پشتیبانی — ${m.author}`} · {formatDateTime(m.created_at)}
              </p>
              <p className="whitespace-pre-wrap break-words">{m.body}</p>
            </div>
          </li>
        ))}
      </ol>
      <Card>
        <CardContent className="space-y-3">
          <label htmlFor="reply" className="text-sm font-medium">
            {ticket.status === "closed" ? "این درخواست بسته شده؛ با پاسخ شما دوباره بررسی می‌شود." : "پاسخ شما"}
          </label>
          <Textarea id="reply" rows={4} maxLength={5000} value={reply} onChange={(e) => setReply(e.target.value)} />
          <div className="flex justify-end">
            <Button onClick={() => void send()} disabled={pending || reply.trim().length < 2}>
              {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
              ارسال
            </Button>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
