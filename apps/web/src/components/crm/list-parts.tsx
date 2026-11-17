import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative w-full sm:w-72">
      <Search
        aria-hidden
        className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="ps-9"
      />
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground">
      <span>{formatNumber(total)} مورد</span>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon-sm" aria-label="صفحه قبل" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronRight />
        </Button>
        <span>
          صفحه {formatNumber(page)} از {formatNumber(pages)}
        </span>
        <Button variant="outline" size="icon-sm" aria-label="صفحه بعد" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          <ChevronLeft />
        </Button>
      </div>
    </div>
  );
}

export function SkeletonRows({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <TableRow key={r}>
          {Array.from({ length: columns }, (_, c) => (
            <TableCell key={c}>
              <Skeleton className="h-4 w-full max-w-32" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

export function EmptyRow({ columns, children }: { columns: number; children: ReactNode }) {
  return (
    <TableRow>
      <TableCell colSpan={columns} className="py-12 text-center text-muted-foreground">
        {children}
      </TableCell>
    </TableRow>
  );
}
