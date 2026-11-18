"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";

import { EmptyRow, Pagination, SkeletonRows } from "@/components/crm/list-parts";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import {
  BLOCK_BY_KIND,
  EXECUTION_STATUS_LABELS,
  SUBJECT_LABELS,
  type BlockKind,
  type Execution,
  type ExecutionLogEntry,
  type ExecutionStatus,
  type RuleVersion,
} from "@/lib/automation";
import { formatDateTime, formatNumber } from "@/lib/format";
import { toQuery } from "@/lib/queries";
import type { Page } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ExecutionStatusBadge } from "./parts";

const SUBJECT_PATH: Record<string, string> = { lead: "/leads", customer: "/customers", deal: "/deals" };

const RESULT_LABELS: Record<string, string> = {
  done: "انجام شد",
  passed: "شرط برقرار بود",
  not_met: "شرط برقرار نبود",
  skipped: "رد شد",
  failed: "ناموفق",
};

function stepLabel(entry: ExecutionLogEntry): string {
  if (entry.type === "recheck") return "بررسی دوباره پس از تأخیر";
  return BLOCK_BY_KIND[entry.type as BlockKind]?.label ?? entry.type;
}

/** Run history of a rule: every run is tied to the version and the record it ran on. */
export function ExecutionHistory({ ruleId }: { ruleId: string }) {
  const [status, setStatus] = useState<ExecutionStatus | "">("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const { data, isPending } = useQuery({
    queryKey: ["automations", ruleId, "executions", status, page],
    queryFn: () =>
      apiFetch<Page<Execution>>(`/automations/${ruleId}/executions${toQuery({ status, page, page_size: 25 })}`),
    placeholderData: (previous) => previous,
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="exec-status" className="text-sm text-muted-foreground">
          وضعیت:
        </label>
        <NativeSelect
          id="exec-status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as ExecutionStatus | "");
            setPage(1);
          }}
        >
          <NativeSelectOption value="">همه</NativeSelectOption>
          {Object.entries(EXECUTION_STATUS_LABELS).map(([value, label]) => (
            <NativeSelectOption key={value} value={value}>
              {label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>زمان</TableHead>
                <TableHead>پرونده</TableHead>
                <TableHead>نسخه</TableHead>
                <TableHead>وضعیت</TableHead>
                <TableHead>توضیح</TableHead>
                <TableHead>
                  <span className="sr-only">جزئیات</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isPending || !data ? (
                <SkeletonRows columns={6} />
              ) : data.items.length === 0 ? (
                <EmptyRow columns={6}>هنوز اجرایی ثبت نشده است. اجرا فقط برای رویدادهای پس از انتشار رخ می‌دهد.</EmptyRow>
              ) : (
                data.items.map((e) => {
                  const href = SUBJECT_PATH[e.subject_type] ? `${SUBJECT_PATH[e.subject_type]}/${e.subject_id}` : null;
                  const expanded = open === e.id;
                  return (
                    <Fragment key={e.id}>
                      <TableRow>
                        <TableCell className="whitespace-nowrap">{formatDateTime(e.created_at)}</TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground">{SUBJECT_LABELS[e.subject_type]}: </span>
                          {e.subject_name && href ? (
                            <Link href={href} className="hover:underline">
                              {e.subject_name}
                            </Link>
                          ) : (
                            e.subject_name ?? "—"
                          )}
                        </TableCell>
                        <TableCell>{formatNumber(e.version_number)}</TableCell>
                        <TableCell>
                          <ExecutionStatusBadge status={e.status} />
                        </TableCell>
                        <TableCell className="max-w-72 truncate text-sm text-muted-foreground">
                          {e.error ?? (e.status === "waiting" && e.resume_at ? `ادامه در ${formatDateTime(e.resume_at)}` : "")}
                        </TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-expanded={expanded}
                            aria-label="جزئیات قدم‌ها"
                            onClick={() => setOpen(expanded ? null : e.id)}
                          >
                            <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expanded ? (
                        <TableRow className="bg-muted/30 hover:bg-muted/30">
                          <TableCell colSpan={6}>
                            {e.log.length === 0 ? (
                              <p className="text-sm text-muted-foreground">قدمی اجرا نشد.</p>
                            ) : (
                              <ol className="space-y-1 text-sm">
                                {e.log.map((entry, i) => (
                                  <li key={i} className="flex flex-wrap gap-x-2">
                                    <span className="font-medium">
                                      {formatNumber(entry.step + 1)}. {stepLabel(entry)}
                                    </span>
                                    <span className={cn(entry.result === "failed" && "text-destructive")}>
                                      {RESULT_LABELS[entry.result] ?? entry.result}
                                    </span>
                                    {entry.detail ? <span className="text-muted-foreground">— {entry.detail}</span> : null}
                                    <span className="text-xs text-muted-foreground">{formatDateTime(entry.at)}</span>
                                  </li>
                                ))}
                              </ol>
                            )}
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      {data && data.total > data.page_size ? (
        <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      ) : null}
    </div>
  );
}

export function VersionList({ ruleId }: { ruleId: string }) {
  const { data, isPending } = useQuery({
    queryKey: ["automations", ruleId, "versions"],
    queryFn: () => apiFetch<RuleVersion[]>(`/automations/${ruleId}/versions`),
  });
  return (
    <Card className="py-0">
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>نسخه</TableHead>
              <TableHead>منتشرکننده</TableHead>
              <TableHead>زمان انتشار</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isPending || !data ? (
              <SkeletonRows columns={3} rows={2} />
            ) : data.length === 0 ? (
              <EmptyRow columns={3}>هنوز منتشر نشده است.</EmptyRow>
            ) : (
              data.map((v, i) => (
                <TableRow key={v.id}>
                  <TableCell>
                    {formatNumber(v.number)}
                    {i === 0 ? <span className="ms-2 text-xs text-primary">آخرین</span> : null}
                  </TableCell>
                  <TableCell>{v.published_by.full_name}</TableCell>
                  <TableCell>{formatDateTime(v.published_at)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
