"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";

import { LimitedMark, Owner } from "@/components/crm/bits";
import { CustomerFormDialog } from "@/components/crm/customer-form-dialog";
import { EmptyRow, Pagination, SearchInput, SkeletonRows } from "@/components/crm/list-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatMobile } from "@/lib/format";
import { useCustomers, useTags } from "@/lib/queries";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

const COLUMNS = 6;

export function CustomersView() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [tagId, setTagId] = useState("");
  const [mine, setMine] = useState(false);
  const [page, setPage] = useState(1);
  const search = useDebounced(q.trim());
  const { data: tags = [] } = useTags();
  const { data, isPending, isError, error } = useCustomers({ q: search, tag_id: tagId, mine, page });

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(1);
  };

  return (
    <>
      <PageHeader
        title="مشتریان"
        description="اشخاص، سازمان‌ها و سابقه ارتباط."
        actions={
          <CustomerFormDialog
            trigger={
              <Button>
                <Plus aria-hidden />
                مشتری جدید
              </Button>
            }
          />
        }
      />

      <Card className="gap-0 py-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <SearchInput value={q} onChange={resetPage(setQ)} placeholder="جست‌وجوی نام یا شماره کامل" />
          <NativeSelect aria-label="برچسب" value={tagId} onChange={(e) => resetPage(setTagId)(e.target.value)}>
            <NativeSelectOption value="">همه برچسب‌ها</NativeSelectOption>
            {tags.map((t) => (
              <NativeSelectOption key={t.id} value={t.id}>
                {t.name}
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
              <TableHead className="hidden md:table-cell">سازمان</TableHead>
              <TableHead>موبایل</TableHead>
              <TableHead className="hidden lg:table-cell">برچسب‌ها</TableHead>
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
              data.items.map((c) => {
                const full = c.access === "full";
                return (
                  <TableRow key={c.id} onClick={() => router.push(`/customers/${c.id}`)} className="cursor-pointer">
                    <TableCell className="font-medium">
                      <span className="flex items-center gap-1.5">
                        {c.full_name}
                        {full ? null : <LimitedMark />}
                      </span>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      {full && c.organizations.length
                        ? c.organizations.map((o) => o.organization.name).join("، ")
                        : "—"}
                    </TableCell>
                    <TableCell className="ltr-value text-end">{full ? formatMobile(c.mobile) : "—"}</TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {full ? (
                        <span className="flex flex-wrap gap-1">
                          {c.tags.map((t) => (
                            <Badge key={t.id} variant="secondary" className="bg-accent text-accent-foreground">
                              {t.name}
                            </Badge>
                          ))}
                        </span>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <Owner user={c.owner} />
                    </TableCell>
                    <TableCell className="hidden md:table-cell">{formatDate(c.created_at)}</TableCell>
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
