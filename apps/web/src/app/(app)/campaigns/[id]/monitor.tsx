"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { EmptyRow, Pagination, SkeletonRows } from "@/components/crm/list-parts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import {
  CHANNEL_LABELS,
  RECIPIENT_STATUS_LABELS,
  type Campaign,
  type Recipient,
  type RecipientStatus,
} from "@/lib/campaigns";
import { formatDateTime, formatMobile, formatNumber, formatToman } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CampaignStatusBadge, ProgressBar } from "../parts";
import { CampaignActions, WaitingNotice } from "./actions";

const RECIPIENT_STYLES: Record<RecipientStatus, string> = {
  pending: "bg-secondary text-secondary-foreground",
  skipped: "bg-muted text-muted-foreground",
  in_queue: "bg-sky-50 text-sky-800",
  accepted: "bg-emerald-50 text-emerald-800",
  delivered: "bg-success text-success-foreground",
  failed: "bg-destructive/10 text-destructive",
  unknown: "bg-amber-100 text-amber-900",
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="py-4">
      <CardContent className="space-y-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
        {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

/** A campaign after it started: progress, each recipient's result (criterion 8). */
export function CampaignMonitor({ campaign }: { campaign: Campaign }) {
  const s = campaign.stats;
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{campaign.name}</h1>
          <CampaignStatusBadge status={campaign.status} />
          <span className="text-sm text-muted-foreground">{CHANNEL_LABELS[campaign.channel]}</span>
        </div>
        <CampaignActions campaign={campaign} />
      </div>
      <WaitingNotice campaign={campaign} />
      {campaign.status !== "scheduled" ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="گیرندگان" value={formatNumber(s.total)} hint={`${formatNumber(s.skipped)} ارسال نشد`} />
            <Stat
              label="پذیرفته یا تحویل‌شده"
              value={formatNumber(s.accepted + s.delivered)}
              hint="پذیرش سرویس‌دهنده به معنی تحویل نیست"
            />
            <Stat label="تحویل‌شده (با گزارش)" value={formatNumber(s.delivered)} />
            <Stat label="هزینه برآوردی" value={formatToman(s.cost)} hint={`${formatNumber(s.failed)} ناموفق`} />
          </div>
          <Card>
            <CardContent>
              <ProgressBar stats={s} legend />
            </CardContent>
          </Card>
        </>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <RecipientTable campaign={campaign} />
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>پیام</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {campaign.subject ? <p className="font-medium">موضوع: {campaign.subject}</p> : null}
            <p className="whitespace-pre-wrap break-words rounded-lg bg-muted px-3 py-2 leading-6">{campaign.body}</p>
            <dl className="space-y-1 pt-2 text-xs text-muted-foreground">
              <div>سازنده: {campaign.created_by.full_name}</div>
              {campaign.started_at ? <div>شروع: {formatDateTime(campaign.started_at)}</div> : null}
              {campaign.finished_at ? <div>پایان: {formatDateTime(campaign.finished_at)}</div> : null}
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function RecipientTable({ campaign }: { campaign: Campaign }) {
  const [status, setStatus] = useState<RecipientStatus | "">("");
  const [page, setPage] = useState(1);
  const { data, isPending } = useQuery({
    queryKey: ["campaigns", campaign.id, "recipients", status, page, campaign.stats],
    queryFn: () =>
      apiFetch<Page<Recipient>>(`/campaigns/${campaign.id}/recipients${toQuery({ status, page, page_size: 50 })}`),
    placeholderData: (previous) => previous,
    enabled: campaign.status !== "scheduled",
  });
  if (campaign.status === "scheduled") return <div />;

  return (
    <Card className="gap-3 py-0">
      <CardContent className="space-y-3 px-0 pt-4">
        <div className="flex flex-wrap items-center gap-2 px-4">
          <h2 className="font-semibold">نتیجه هر گیرنده</h2>
          <NativeSelect
            aria-label="وضعیت"
            className="ms-auto"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as RecipientStatus | "");
              setPage(1);
            }}
          >
            <NativeSelectOption value="">همه</NativeSelectOption>
            {Object.entries(RECIPIENT_STATUS_LABELS).map(([value, label]) => (
              <NativeSelectOption key={value} value={value}>
                {label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>مخاطب</TableHead>
              <TableHead>نشانی</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead>توضیح</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending || !data ? (
              <SkeletonRows columns={4} rows={4} />
            ) : data.items.length === 0 ? (
              <EmptyRow columns={4}>موردی نیست.</EmptyRow>
            ) : (
              data.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link href={`/${r.contact_type === "lead" ? "leads" : "customers"}/${r.contact_id}`} className="hover:underline">
                      {r.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="ltr-value text-xs">
                      {r.address ? (campaign.channel === "sms" ? formatMobile(r.address) : r.address) : "—"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className={cn("font-medium", RECIPIENT_STYLES[r.status])}>
                      {RECIPIENT_STATUS_LABELS[r.status]}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-64 text-xs text-muted-foreground">
                    {r.reason ??
                      (r.delivered_at
                        ? `تحویل ${formatDateTime(r.delivered_at)}`
                        : r.sent_at
                          ? `ارسال ${formatDateTime(r.sent_at)}`
                          : "")}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        {data && data.total > data.page_size ? (
          <div className="px-4 pb-3">
            <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
