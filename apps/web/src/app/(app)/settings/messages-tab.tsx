"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";

import { Pagination } from "@/components/crm/list-parts";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatNumber } from "@/lib/format";
import { useSettings } from "@/lib/queries";
import type { Page } from "@/lib/types";

type Message = {
  id: string;
  channel: "sms" | "email";
  purpose: "otp" | "notification";
  recipient: string;
  subject: string | null;
  status: "queued" | "sending" | "accepted" | "delivered" | "failed" | "unknown" | "expired";
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
  delivered_at: string | null;
};

const STATUS: Record<Message["status"], { label: string; className: string }> = {
  queued: { label: "در صف", className: "bg-secondary text-secondary-foreground" },
  sending: { label: "در حال ارسال", className: "bg-sky-50 text-sky-800" },
  accepted: { label: "پذیرفته‌شده توسط سرویس", className: "bg-sky-50 text-sky-800" },
  delivered: { label: "تحویل‌شده", className: "bg-success text-success-foreground" },
  failed: { label: "ناموفق", className: "bg-destructive/10 text-destructive" },
  unknown: { label: "نامشخص — نیاز به بررسی", className: "bg-warning text-warning-foreground" },
  expired: { label: "منقضی؛ ارسال نشد", className: "bg-muted text-muted-foreground" },
};

/** Delivery log (spec 7, 10): "accepted" is not "delivered", and "unknown" is never retried blindly. */
export function MessagesTab() {
  const [status, setStatus] = useState("");
  const [channel, setChannel] = useState("");
  const [page, setPage] = useState(1);
  const { data, isPending } = useSettings<Page<Message>>("/messages", { status, channel, page });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          پیامک و ایمیل‌های ارسالی و وضعیت تحویل. در محیط توسعه پیام‌ها به{" "}
          <a href="http://localhost:8030" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            صندوق پیامک آزمایشی <ExternalLink className="size-3" aria-hidden />
          </a>{" "}
          و{" "}
          <a href="http://localhost:8025" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            Mailpit <ExternalLink className="size-3" aria-hidden />
          </a>{" "}
          می‌روند و واقعاً ارسال نمی‌شوند.
        </p>
        <div className="flex gap-2">
          <NativeSelect aria-label="کانال" value={channel} onChange={(e) => { setChannel(e.target.value); setPage(1); }}>
            <NativeSelectOption value="">همه کانال‌ها</NativeSelectOption>
            <NativeSelectOption value="sms">پیامک</NativeSelectOption>
            <NativeSelectOption value="email">ایمیل</NativeSelectOption>
          </NativeSelect>
          <NativeSelect aria-label="وضعیت" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <NativeSelectOption value="">همه وضعیت‌ها</NativeSelectOption>
            {(Object.keys(STATUS) as Message["status"][]).map((s) => (
              <NativeSelectOption key={s} value={s}>{STATUS[s].label}</NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      </div>
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>زمان</TableHead>
              <TableHead>کانال / نوع</TableHead>
              <TableHead>گیرنده</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead>تلاش</TableHead>
              <TableHead>خطای آخر</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending || !data ? (
              <TableRow><TableCell colSpan={6}><Skeleton className="h-24" /></TableCell></TableRow>
            ) : data.items.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="py-10 text-center text-muted-foreground">پیامی ارسال نشده است.</TableCell></TableRow>
            ) : (
              data.items.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="whitespace-nowrap">{formatDateTime(m.created_at)}</TableCell>
                  <TableCell>
                    {m.channel === "sms" ? "پیامک" : "ایمیل"} · {m.purpose === "otp" ? "کد ورود" : "اعلان"}
                  </TableCell>
                  <TableCell className="ltr-value">{m.recipient}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={STATUS[m.status].className}>{STATUS[m.status].label}</Badge>
                  </TableCell>
                  <TableCell>{formatNumber(m.attempts)}</TableCell>
                  <TableCell className="max-w-56 truncate text-xs text-muted-foreground" title={m.last_error ?? undefined}>
                    <span dir="ltr">{m.last_error ?? "—"}</span>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
      {data && data.total > data.page_size ? <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} /> : null}
    </div>
  );
}
