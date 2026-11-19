"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Columns3, List, Plus } from "lucide-react";

import { LimitedMark, Owner } from "@/components/crm/bits";
import { BoardSkeleton, DealBoard } from "@/components/crm/deal-board";
import { DealFormDialog } from "@/components/crm/deal-form-dialog";
import { DealStatusBadge } from "@/components/crm/deal-status";
import { EmptyRow, Pagination, SearchInput, SkeletonRows } from "@/components/crm/list-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatToman } from "@/lib/format";
import { canManage, useAssignableUsers, useBoard, useDeals, useMe, useStages } from "@/lib/queries";
import type { DealStatus } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

type View = "board" | "list";

const CLOSED_RANGES = [
  { days: 30, label: "۳۰ روز اخیر" },
  { days: 90, label: "۹۰ روز اخیر" },
  { days: 365, label: "یک سال اخیر" },
];

export function DealsView() {
  const [view, setView] = useState<View>("board");
  const [q, setQ] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [mine, setMine] = useState(false);
  const [closedDays, setClosedDays] = useState(30);
  const search = useDebounced(q.trim());
  const { data: me } = useMe();
  const { data: users = [] } = useAssignableUsers();
  const hydrated = useHydrated();
  // Role-based controls appear after hydration, so server and client markup match.
  const manager = hydrated && canManage(me?.role);

  return (
    <>
      <PageHeader
        title={view === "board" ? "تابلوی فروش" : "فروش‌ها"}
        description="هر فروش از مرحله «بررسی نیاز» تا نتیجه نهایی."
        actions={
          <DealFormDialog
            trigger={
              <Button>
                <Plus aria-hidden />
                فروش جدید
              </Button>
            }
          />
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border bg-card p-0.5" role="radiogroup" aria-label="نوع نمایش">
          {(
            [
              { value: "board", label: "تابلو", icon: Columns3 },
              { value: "list", label: "فهرست", icon: List },
            ] as const
          ).map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={view === value}
              onClick={() => setView(value)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm",
                view === value ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </button>
          ))}
        </div>
        <SearchInput value={q} onChange={setQ} placeholder="جست‌وجوی عنوان یا مشتری" />
        {manager ? (
          <NativeSelect aria-label="کارشناس" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
            <NativeSelectOption value="">همه کارشناسان</NativeSelectOption>
            {users.map((u) => (
              <NativeSelectOption key={u.id} value={u.id}>
                {u.full_name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : (
          <Button
            variant="ghost"
            aria-pressed={mine}
            onClick={() => setMine(!mine)}
            className={cn(mine && "bg-accent text-accent-foreground")}
          >
            فقط موارد من
          </Button>
        )}
        {view === "board" ? (
          <NativeSelect
            aria-label="بازه نتیجه نهایی"
            value={closedDays}
            onChange={(e) => setClosedDays(Number(e.target.value))}
          >
            {CLOSED_RANGES.map((r) => (
              <NativeSelectOption key={r.days} value={r.days}>
                نتیجه: {r.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : null}
      </div>

      {view === "board" ? (
        <BoardView params={{ q: search, owner_id: ownerId, mine, closed_days: closedDays }} />
      ) : (
        <ListView filters={{ q: search, owner_id: ownerId, mine }} />
      )}
    </>
  );
}

function BoardView({ params }: { params: Record<string, string | number | boolean> }) {
  const { data: board, isPending, error } = useBoard(params);
  const { data: stages = [] } = useStages();
  if (isPending) return <BoardSkeleton />;
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  return <DealBoard board={board} stages={stages} />;
}

const COLUMNS = 6;

function ListView({ filters }: { filters: Record<string, string | boolean> }) {
  const router = useRouter();
  const [status, setStatus] = useState<DealStatus | "">("");
  const [page, setPage] = useState(1);
  const { data, isPending, isError, error } = useDeals({ ...filters, status, page });

  return (
    <Card className="gap-0 py-0">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <NativeSelect
          aria-label="وضعیت"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as DealStatus | "");
            setPage(1);
          }}
        >
          <NativeSelectOption value="">همه</NativeSelectOption>
          <NativeSelectOption value="open">باز</NativeSelectOption>
          <NativeSelectOption value="won">فروش انجام شد</NativeSelectOption>
          <NativeSelectOption value="lost">به نتیجه نرسید</NativeSelectOption>
        </NativeSelect>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>عنوان</TableHead>
            <TableHead>مشتری</TableHead>
            <TableHead>مرحله / نتیجه</TableHead>
            <TableHead>مبلغ</TableHead>
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
            <EmptyRow columns={COLUMNS}>فروشی پیدا نشد.</EmptyRow>
          ) : (
            data.items.map((deal) => {
              const full = deal.access === "full" ? deal : null;
              const amount = full ? (full.status === "won" ? full.contract_amount : full.amount) : null;
              return (
                <TableRow key={deal.id} onClick={() => router.push(`/deals/${deal.id}`)} className="cursor-pointer">
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-1.5">
                      {deal.title}
                      {full ? null : <LimitedMark />}
                    </span>
                  </TableCell>
                  <TableCell>{deal.customer.full_name}</TableCell>
                  <TableCell>
                    <DealStatusBadge deal={deal} />
                  </TableCell>
                  <TableCell>{amount !== null ? formatToman(amount) : "—"}</TableCell>
                  <TableCell>
                    <Owner user={deal.owner} />
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{formatDate(deal.created_at)}</TableCell>
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
  );
}
