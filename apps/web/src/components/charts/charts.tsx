"use client";

import { useState, type ReactNode } from "react";
import { Table2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Series = { key: string; label: string; color: string; values: number[] };

/** Rounds an axis maximum up to 1, 2, 2.5 or 5 × 10ⁿ. */
function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * power >= value)!;
  return step * power;
}

/** «۱۲۰ م» / «۳٫۵ ه» style compact amounts for axis ticks (toman). */
export function compactToman(value: number): string {
  if (value >= 1e9) return `${formatNumber(Math.round((value / 1e9) * 10) / 10)} میلیارد`;
  if (value >= 1e6) return `${formatNumber(Math.round((value / 1e6) * 10) / 10)} میلیون`;
  if (value >= 1e3) return `${formatNumber(Math.round(value / 1e3))} هزار`;
  return formatNumber(value);
}

export function Legend({ series }: { series: Pick<Series, "key" | "label" | "color">[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="راهنما">
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

function TableToggle({ shown, onToggle }: { shown: boolean; onToggle: () => void }) {
  return (
    <Button variant="ghost" size="sm" onClick={onToggle} aria-pressed={shown} className="text-muted-foreground">
      <Table2 aria-hidden />
      {shown ? "نمایش نمودار" : "نمایش جدول"}
    </Button>
  );
}

/**
 * Columns over time (single or stacked). Time reads left→right as in the reference
 * screens; one y-axis; hairline grid; ≤24px columns with a 4px rounded top; 2px
 * surface gaps between stacked segments; a tooltip per column on hover or focus.
 */
export function ColumnChart({
  labels,
  series,
  format,
  axisFormat = format,
  height = 220,
  caption,
}: {
  labels: string[];
  series: Series[];
  format: (v: number) => string;
  axisFormat?: (v: number) => string;
  height?: number;
  caption: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const totals = labels.map((_, i) => series.reduce((s, x) => s + (x.values[i] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const stacked = series.length > 1;

  return (
    <figure className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {stacked ? <Legend series={series} /> : <span />}
        <TableToggle shown={table} onToggle={() => setTable(!table)} />
      </div>
      {totals.every((t) => t === 0) ? (
        <p className="grid place-items-center rounded-lg border border-dashed text-sm text-muted-foreground" style={{ height }}>
          داده‌ای برای این بازه ثبت نشده است.
        </p>
      ) : table ? (
        <DataTable
          caption={caption}
          head={["دوره", ...series.map((s) => s.label), ...(stacked ? ["جمع"] : [])]}
          rows={labels.map((label, i) => [label, ...series.map((s) => format(s.values[i] ?? 0)), ...(stacked ? [format(totals[i])] : [])])}
        />
      ) : (
        <div className="flex gap-2 pt-3" dir="ltr">
          {/* y-axis */}
          <div className="relative w-16 shrink-0 text-[11px] text-muted-foreground" style={{ height }} aria-hidden>
            {ticks.map((t) => (
              <span key={t} className="absolute end-1 -translate-y-1/2" style={{ bottom: `${(t / max) * 100}%` }} dir="rtl">
                {axisFormat(t)}
              </span>
            ))}
          </div>
          <div className="min-w-0 flex-1">
            <div className="relative border-b" style={{ height, borderColor: "var(--chart-axis)" }}>
              {ticks.slice(1).map((t) => (
                <div
                  key={t}
                  className="absolute inset-x-0 border-t"
                  style={{ bottom: `${(t / max) * 100}%`, borderColor: "var(--chart-grid)" }}
                  aria-hidden
                />
              ))}
              <div className="absolute inset-0 flex items-end">
                {labels.map((label, i) => (
                  <div
                    key={label}
                    className="relative flex h-full flex-1 items-end justify-center"
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                  >
                    <button
                      type="button"
                      onFocus={() => setHover(i)}
                      onBlur={() => setHover(null)}
                      aria-label={`${label}: ${series.map((s) => `${s.label} ${format(s.values[i] ?? 0)}`).join("، ")}`}
                      className={cn(
                        "flex w-full max-w-6 flex-col-reverse gap-[2px] outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                        hover !== null && hover !== i && "opacity-60",
                      )}
                      style={{ height: `${(totals[i] / max) * 100}%` }}
                    >
                      {series.map((s, si) => {
                        const v = s.values[i] ?? 0;
                        if (!v) return null;
                        const top = series.slice(si + 1).every((x) => !(x.values[i] ?? 0));
                        return (
                          <span
                            key={s.key}
                            className={cn("block w-full", top && "rounded-t")}
                            style={{ background: s.color, flexGrow: v, flexBasis: 0, minHeight: 2 }}
                          />
                        );
                      })}
                    </button>
                    {hover === i ? (
                      <div
                        dir="rtl"
                        className="pointer-events-none absolute bottom-full z-10 mb-1 min-w-36 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md"
                      >
                        <p className="mb-1 font-semibold">{label}</p>
                        {series.map((s) => (
                          <p key={s.key} className="flex items-center justify-between gap-3">
                            <span className="flex items-center gap-1.5">
                              <span className="size-2 rounded-sm" style={{ background: s.color }} />
                              {s.label}
                            </span>
                            <span className="font-medium">{format(s.values[i] ?? 0)}</span>
                          </p>
                        ))}
                        {stacked ? (
                          <p className="mt-1 flex justify-between border-t pt-1 font-semibold">
                            <span>جمع</span>
                            <span>{format(totals[i])}</span>
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex pt-1.5 text-[11px] text-muted-foreground" aria-hidden>
              {labels.map((label, i) => (
                <span
                  key={label}
                  className="flex-1 truncate text-center"
                  dir="rtl"
                  // Thin out labels when there are many columns.
                  style={{ visibility: labels.length > 12 && i % Math.ceil(labels.length / 12) ? "hidden" : "visible" }}
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}

/** Ranked horizontal bars (single series): label, bar from the start edge, value at the tip. */
export function BarList({
  rows,
  format,
  caption,
  empty = "داده‌ای برای این بازه نیست.",
}: {
  rows: { key: string; label: ReactNode; value: number; detail?: string }[];
  format: (v: number) => string;
  caption: string;
  empty?: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="py-6 text-center text-sm text-muted-foreground">{empty}</p>;
  return (
    <figure>
      <ul className="space-y-3" aria-label={caption}>
        {rows.map((r) => (
          <li key={r.key} className="grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 text-sm">
            <span className="truncate">{r.label}</span>
            <span className="h-2.5 rounded-e bg-muted" aria-hidden>
              <span
                className="block h-full rounded-e"
                style={{ width: `${(r.value / max) * 100}%`, minWidth: r.value ? 4 : 0, background: "var(--series-single)" }}
              />
            </span>
            <span className="text-end text-xs text-muted-foreground" title={r.detail}>
              {format(r.value)}
              {r.detail ? <span className="block">{r.detail}</span> : null}
            </span>
          </li>
        ))}
      </ul>
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}

export function DataTable({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <Table>
      <caption className="sr-only">{caption}</caption>
      <TableHeader>
        <TableRow>
          {head.map((h) => (
            <TableHead key={h}>{h}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={i}>
            {row.map((cell, j) => (
              <TableCell key={j}>{cell}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
