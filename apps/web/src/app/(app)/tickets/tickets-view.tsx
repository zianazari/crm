"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LifeBuoy, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { Field, Owner } from "@/components/crm/bits";
import { CustomerPicker } from "@/components/crm/customer-picker";
import { EmptyRow, Pagination, SearchInput, SkeletonRows } from "@/components/crm/list-parts";
import { TicketStatusBadge } from "@/components/crm/ticket-bits";
import { PageHeader } from "@/components/layout/page-header";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { formatCode, formatDateTime } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { Ticket, TicketDetail } from "@/lib/tickets";
import type { CustomerFull, Page } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

type Filter = "open" | "new" | "in_progress" | "waiting_customer" | "closed" | "all";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "open", label: "باز" },
  { key: "new", label: "جدید" },
  { key: "in_progress", label: "در حال بررسی" },
  { key: "waiting_customer", label: "منتظر مشتری" },
  { key: "closed", label: "بسته‌شده" },
  { key: "all", label: "همه" },
];

export function TicketsView() {
  const [status, setStatus] = useState<Filter>("open");
  const [mine, setMine] = useState(false);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const search = useDebounced(q.trim(), 300);
  const { data, isPending } = useQuery({
    queryKey: ["tickets", "list", status, mine, search, page],
    queryFn: () => apiFetch<Page<Ticket>>(`/tickets${toQuery({ status, mine, q: search, page, page_size: 25 })}`),
    placeholderData: (previous) => previous,
    refetchInterval: 30_000,
  });

  return (
    <>
      <PageHeader
        title="تیکت‌ها"
        description="درخواست‌های پشتیبانی مشتریان از پنل مشتری یا ثبت‌شده توسط کارکنان."
        actions={<NewTicketDialog />}
      />
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="وضعیت">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={status === f.key}
              onClick={() => {
                setStatus(f.key);
                setPage(1);
              }}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm",
                status === f.key ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-primary" checked={mine} onChange={(e) => { setMine(e.target.checked); setPage(1); }} />
          فقط تیکت‌های من
        </label>
        <div className="ms-auto">
          <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="شماره، عنوان یا نام مشتری" />
        </div>
      </div>
      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>شماره</TableHead>
                <TableHead>عنوان</TableHead>
                <TableHead>مشتری</TableHead>
                <TableHead>وضعیت</TableHead>
                <TableHead>مسئول</TableHead>
                <TableHead>آخرین پیام</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending || !data ? (
                <SkeletonRows columns={6} />
              ) : data.items.length === 0 ? (
                <EmptyRow columns={6}>
                  <LifeBuoy className="mx-auto mb-2 size-7" aria-hidden />
                  تیکتی با این شرایط نیست.
                </EmptyRow>
              ) : (
                data.items.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="text-muted-foreground">{formatCode(t.number)}</TableCell>
                    <TableCell className="max-w-72">
                      <Link href={`/tickets/${t.id}`} className="font-medium hover:underline">
                        {t.subject}
                      </Link>
                      {t.opened_by_customer ? <span className="ms-2 text-xs text-muted-foreground">از پنل مشتری</span> : null}
                    </TableCell>
                    <TableCell>
                      <Link href={`/customers/${t.customer.id}`} className="hover:underline">
                        {t.customer.full_name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <TicketStatusBadge status={t.status} />
                    </TableCell>
                    <TableCell>{t.assignee ? <Owner user={t.assignee} /> : <span className="text-muted-foreground">بدون مسئول</span>}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(t.last_message_at)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && data.total > data.page_size ? (
        <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      ) : null}
    </>
  );
}

/** Opened by staff on the customer's behalf, e.g. after a phone call. */
export function NewTicketDialog({ customer: fixed }: { customer?: CustomerFull }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<CustomerFull | null>(fixed ?? null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [pending, setPending] = useState(false);

  async function submit() {
    if (!customer) return;
    setPending(true);
    try {
      const ticket = await apiFetch<TicketDetail>("/tickets", {
        method: "POST",
        body: JSON.stringify({ customer_id: customer.id, subject: subject.trim(), body: body.trim() }),
      });
      router.push(`/tickets/${ticket.id}`);
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
          setCustomer(fixed ?? null);
          setSubject("");
          setBody("");
          setPending(false);
        }
      }}
    >
      <DialogTrigger
        render={
          <Button size={fixed ? "sm" : "default"} variant={fixed ? "outline" : "default"}>
            <Plus aria-hidden />
            تیکت جدید
          </Button>
        }
      />
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>تیکت جدید</DialogTitle>
          <DialogDescription>برای درخواستی که مشتری تلفنی یا حضوری مطرح کرده است.</DialogDescription>
        </DialogHeader>
        {!fixed ? (
          <Field label="مشتری" required>
            <CustomerPicker value={customer} onChange={setCustomer} />
          </Field>
        ) : null}
        <Field label="عنوان" htmlFor="nt-subject" required>
          <Input id="nt-subject" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </Field>
        <Field label="شرح" htmlFor="nt-body" required hint="این متن را مشتری هم در پنل خود می‌بیند.">
          <Textarea id="nt-body" rows={5} maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={pending || !customer || subject.trim().length < 3 || body.trim().length < 2}>
            {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ثبت تیکت
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
