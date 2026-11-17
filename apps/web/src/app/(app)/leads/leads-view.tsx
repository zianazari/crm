"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";

import { LeadStatusBadge, LimitedMark, Owner } from "@/components/crm/bits";
import { LeadFormDialog } from "@/components/crm/lead-form-dialog";
import { EmptyRow, Pagination, SearchInput, SkeletonRows } from "@/components/crm/list-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatMobile } from "@/lib/format";
import { useLeads, useSources } from "@/lib/queries";
import { LEAD_STATUS_LABELS, type LeadStatus } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

const COLUMNS = 6;

export function LeadsView() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<LeadStatus | "">("");
  const [sourceId, setSourceId] = useState("");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);
  const search = useDebounced(q.trim());
  const { data: sources = [] } = useSources();
  const { data, isPending, isError, error } = useLeads({
    q: search,
    status,
    source_id: sourceId,
    mine,
    page,
  });

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  return (
    <>
      <PageHeader
        title="مشتریان احتمالی"
        description="سرنخ‌ها، منبع جذب و وضعیت پیگیری."
        actions={
          <LeadFormDialog
            trigger={
              <Button>
                <Plus aria-hidden />
                مشتری احتمالی جدید
              </Button>
            }
          />
        }
      />

      <Card className="gap-0 py-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <SearchInput value={q} onChange={resetPage(setQ)} placeholder="جست‌وجوی نام یا شماره کامل" />
          <NativeSelect
            aria-label="وضعیت"
            value={status}
            onChange={(e) => resetPage(setStatus)(e.target.value as LeadStatus | "")}
          >
            <NativeSelectOption value="">همه وضعیت‌ها</NativeSelectOption>
            {(Object.keys(LEAD_STATUS_LABELS) as LeadStatus[]).map((s) => (
              <NativeSelectOption key={s} value={s}>
                {LEAD_STATUS_LABELS[s]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <NativeSelect aria-label="منبع جذب" value={sourceId} onChange={(e) => resetPage(setSourceId)(e.target.value)}>
            <NativeSelectOption value="">همه منابع</NativeSelectOption>
            {sources.map((s) => (
              <NativeSelectOption key={s.id} value={s.id}>
                {s.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <Button
            variant={mine ? "secondary" : "ghost"}
            aria-pressed={mine}
            onClick={() => resetPage(setMine)(!mine)}
            className={cn(mine && "bg-accent text-accent-foreground")}
          >
            فقط موارد من
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>نام</TableHead>
              <TableHead>وضعیت</TableHead>
              <TableHead>موبایل</TableHead>
              <TableHead className="hidden md:table-cell">منبع</TableHead>
              <TableHead>مسئول</TableHead>
              <TableHead className="hidden md:table-cell">تاریخ ثبت</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending ? (
              <SkeletonRows columns={COLUMNS} />
            ) : isError ? (
              <EmptyRow columns={COLUMNS}>{error.message}</EmptyRow>
            ) : data.items.length === 0 ? (
              <EmptyRow columns={COLUMNS}>موردی پیدا نشد.</EmptyRow>
            ) : (
              data.items.map((lead) => {
                const full = lead.access === "full";
                return (
                  <TableRow
                    key={lead.id}
                    onClick={() => router.push(`/leads/${lead.id}`)}
                    className="cursor-pointer"
                  >
                    <TableCell className="font-medium">
                      <span className="flex items-center gap-1.5">
                        {lead.full_name}
                        {full ? null : <LimitedMark />}
                      </span>
                      {full && lead.company_name ? (
                        <span className="block text-xs font-normal text-muted-foreground">{lead.company_name}</span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <LeadStatusBadge status={lead.status} />
                    </TableCell>
                    <TableCell className="ltr-value text-end">{full ? formatMobile(lead.mobile) : "—"}</TableCell>
                    <TableCell className="hidden md:table-cell">{full ? (lead.source?.name ?? "—") : "—"}</TableCell>
                    <TableCell>
                      <Owner user={lead.owner} />
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{formatDate(lead.created_at)}</TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {data && data.total > 0 ? (
          <div className="border-t p-3">
            <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          </div>
        ) : null}
      </Card>
    </>
  );
}
