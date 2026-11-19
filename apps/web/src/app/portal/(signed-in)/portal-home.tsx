"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Inbox, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Field } from "@/components/crm/bits";
import { Pagination } from "@/components/crm/list-parts";
import { TicketStatusBadge } from "@/components/crm/ticket-bits";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { formatCode, formatDateTime } from "@/lib/format";
import { portalFetch, type PortalTicketDetail, type PortalTicketPage } from "@/lib/portal";
import { usePortalMe } from "./portal-header";

export function PortalHome() {
  const { data: me } = usePortalMe();
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: ["portal", "tickets", page],
    queryFn: () => portalFetch<PortalTicketPage>(`/tickets?page=${page}&page_size=20`),
    placeholderData: (previous) => previous,
  });

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">{me ? `${me.customer_name}، خوش آمدید` : "درخواست‌های من"}</h1>
          <p className="text-sm text-muted-foreground">درخواست پشتیبانی ثبت کنید و پاسخ‌ها را همین‌جا ببینید.</p>
        </div>
        <NewTicketDialog />
      </div>
      {isPending || !data ? (
        <Skeleton className="h-40" />
      ) : data.items.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
            <Inbox className="size-8 text-muted-foreground" aria-hidden />
            <p className="font-medium">هنوز درخواستی ثبت نکرده‌اید</p>
            <p className="text-sm text-muted-foreground">با «درخواست جدید» سؤال یا مشکل خود را بنویسید.</p>
          </CardContent>
        </Card>
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {data.items.map((t) => (
            <li key={t.id}>
              <Link href={`/portal/tickets/${t.id}`} className="flex items-center gap-3 p-4 hover:bg-muted/40 focus-visible:bg-muted/60 focus-visible:outline-none">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{t.subject}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    شماره {formatCode(t.number)} · آخرین پیام {formatDateTime(t.last_message_at)}
                  </p>
                </div>
                <TicketStatusBadge status={t.status} label={t.status_label} />
                <ChevronLeft className="size-4 text-muted-foreground" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {data && data.total > data.page_size ? (
        <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      ) : null}
    </>
  );
}

function NewTicketDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [pending, setPending] = useState(false);

  async function submit() {
    setPending(true);
    try {
      const ticket = await portalFetch<PortalTicketDetail>("/tickets", {
        method: "POST",
        body: JSON.stringify({ subject: subject.trim(), body: body.trim() }),
      });
      toast.success(`درخواست شماره ${formatCode(ticket.number)} ثبت شد.`);
      router.push(`/portal/tickets/${ticket.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "ثبت انجام نشد.");
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setSubject("");
          setBody("");
          setPending(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button>
            <Plus aria-hidden />
            درخواست جدید
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>درخواست جدید</DialogTitle>
          <DialogDescription>پس از ثبت، شماره پیگیری می‌گیرد و پاسخ کارشناس همین‌جا نمایش داده می‌شود.</DialogDescription>
        </DialogHeader>
        <Field label="عنوان" htmlFor="t-subject" required hint="کوتاه؛ مثلاً «اصلاح مبلغ فاکتور».">
          <Input id="t-subject" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </Field>
        <Field label="شرح" htmlFor="t-body" required hint="حداقل ۱۰ نویسه.">
          <Textarea id="t-body" rows={6} maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={pending || subject.trim().length < 3 || body.trim().length < 10}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت درخواست
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
