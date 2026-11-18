"use client";

import { useState } from "react";
import { BarChart3, ChartColumnStacked, CircleX, Link2, Users } from "lucide-react";

import { BarList, ColumnChart, compactToman, DataTable } from "@/components/charts/charts";
import { PageHeader } from "@/components/layout/page-header";
import { PeriodPicker } from "@/components/reports/period-picker";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber, formatToman } from "@/lib/format";
import { formatIsoDate } from "@/lib/jalali";
import { bucketize, buckets, periodLabel, presetPeriod, type Period } from "@/lib/period";
import {
  canManage,
  useAssignableUsers,
  useMe,
  useReport,
  useSources,
  type InboundRow,
  type ListParams,
  type ReportSummary,
} from "@/lib/queries";
import type { UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

const REPORTS = [
  { group: "تحلیل فروش", key: "summary", label: "گزارش کلی فروش", icon: BarChart3 },
  { group: "تحلیل فروش", key: "inbound", label: "معاملات ورودی", icon: ChartColumnStacked },
  { group: "تحلیل فروش", key: "sources", label: "فروش به تفکیک منبع", icon: Link2 },
  { group: "تحلیل فروش", key: "lost", label: "دلایل به نتیجه نرسیدن", icon: CircleX },
  { group: "تحلیل تیم", key: "team", label: "عملکرد کارشناسان", icon: Users },
] as const;

type ReportKey = (typeof REPORTS)[number]["key"];

const percent = (rate: number | null) => (rate === null ? "—" : `${formatNumber(Math.round(rate * 1000) / 10)}٪`);

export function ReportsView({ today }: { today: string }) {
  const [report, setReport] = useState<ReportKey>("summary");
  const [period, setPeriod] = useState<Period>(() => presetPeriod("this_month", today));
  const [ownerId, setOwnerId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const { data: me } = useMe();
  const { data: users = [] } = useAssignableUsers();
  const { data: sources = [] } = useSources();
  const filters: ListParams = {
    date_from: period.from,
    date_to: period.to,
    owner_id: ownerId || undefined,
    source_id: sourceId || undefined,
  };
  const current = REPORTS.find((r) => r.key === report)!;

  return (
    <>
      <PageHeader title="گزارش‌ها" description="اعداد فقط از پرونده‌هایی محاسبه می‌شوند که به آنها دسترسی کامل دارید." />

      <div className="grid gap-6 lg:grid-cols-[14rem_1fr]">
        <nav aria-label="فهرست گزارش‌ها" className="space-y-4">
          {["تحلیل فروش", "تحلیل تیم"].map((group) => (
            <div key={group} className="space-y-1">
              <p className="px-2 text-xs font-medium text-muted-foreground">{group}</p>
              {REPORTS.filter((r) => r.group === group).map((r) => (
                <button
                  key={r.key}
                  onClick={() => setReport(r.key)}
                  aria-current={report === r.key ? "page" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-start text-sm",
                    report === r.key ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted",
                  )}
                >
                  <r.icon className="size-4" aria-hidden />
                  {r.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <PeriodPicker value={period} onChange={setPeriod} today={today} />
            {canManage(me?.role) ? (
              <NativeSelect aria-label="کارشناس" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
                <NativeSelectOption value="">همه کارشناسان</NativeSelectOption>
                {users.map((u) => (
                  <NativeSelectOption key={u.id} value={u.id}>
                    {u.full_name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            ) : null}
            <NativeSelect aria-label="منبع جذب" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              <NativeSelectOption value="">همه منابع</NativeSelectOption>
              {sources.map((s) => (
                <NativeSelectOption key={s.id} value={s.id}>
                  {s.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>

          <h2 className="text-lg font-semibold">
            {current.label} <span className="text-sm font-normal text-muted-foreground">— {periodLabel(period)}</span>
          </h2>

          {report === "summary" ? <SummaryReport filters={filters} period={period} /> : null}
          {report === "inbound" ? <InboundReport filters={filters} period={period} /> : null}
          {report === "sources" ? <SourcesReport filters={filters} /> : null}
          {report === "lost" ? <LostReport filters={filters} /> : null}
          {report === "team" ? <TeamReport filters={filters} /> : null}
        </div>
      </div>
    </>
  );
}

function Stat({ label, value, note }: { label: string; value: string | undefined; note?: string }) {
  return (
    <Card className="py-4">
      <CardContent className="space-y-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        {value === undefined ? <Skeleton className="h-6 w-24" /> : <p className="text-xl font-bold">{value}</p>}
        {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      </CardContent>
    </Card>
  );
}

function SummaryReport({ filters, period }: { filters: ListParams; period: Period }) {
  const { data: s } = useReport<ReportSummary>("summary", filters);
  const { data: sales } = useReport<{ date: string; value: number }[]>("series", { ...filters, metric: "sales_amount" });
  const { data: received } = useReport<{ date: string; value: number }[]>("series", { ...filters, metric: "received" });
  const list = buckets(period.from, period.to);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="فروش (بر اساس تاریخ قرارداد)" value={s && formatToman(s.sales.amount)} note={s && `${formatNumber(s.sales.count)} قرارداد`} />
        <Stat label="دریافتی (پس از بازپرداخت)" value={s && formatToman(s.received)} />
        <Stat label="مانده دریافت‌نشده (تا امروز)" value={s && formatToman(s.unpaid_balance)} />
        <Stat label="فروش بالقوه (فروش‌های باز)" value={s && formatToman(s.pipeline.amount)} note={s && `${formatNumber(s.pipeline.count)} فروش باز`} />
        <Stat
          label="نرخ برد"
          value={s && percent(s.win_rate.rate)}
          note={s && `${formatNumber(s.win_rate.numerator)} موفق از ${formatNumber(s.win_rate.denominator)} بسته‌شده`}
        />
        <Stat
          label="نرخ تبدیل مشتری احتمالی"
          value={s && percent(s.lead_conversion.rate)}
          note={s && `${formatNumber(s.lead_conversion.numerator)} از ${formatNumber(s.lead_conversion.denominator)} تا ${formatIsoDate(s.evaluated_on)}`}
        />
        <Stat
          label="میانه زمان اولین تماس"
          value={s && (s.first_contact_median_hours === null ? "—" : `${formatNumber(s.first_contact_median_hours)} ساعت`)}
          note="از ثبت مشتری احتمالی تا اولین تماس یا جلسه انجام‌شده"
        />
        <Stat
          label="کارهای معوق / فروش بدون پیگیری"
          value={s && `${formatNumber(s.overdue_activities)} / ${formatNumber(s.deals_without_next_action)}`}
          note="وضعیت امروز"
        />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>فروش</CardTitle>
            <p className="text-xs text-muted-foreground">مبلغ قراردادها بر اساس تاریخ قرارداد — تومان</p>
          </CardHeader>
          <CardContent>
            {sales ? (
              <ColumnChart
                caption="فروش در بازه"
                labels={list.map((b) => b.label)}
                series={[{ key: "s", label: "فروش", color: "var(--series-single)", values: bucketize(sales, list, (p) => p.value) }]}
                format={formatToman}
                axisFormat={compactToman}
              />
            ) : (
              <Skeleton className="h-60" />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>دریافتی</CardTitle>
            <p className="text-xs text-muted-foreground">پرداخت‌ها منهای بازپرداخت، بر اساس تاریخ پرداخت — تومان</p>
          </CardHeader>
          <CardContent>
            {received ? (
              <ColumnChart
                caption="دریافتی در بازه"
                labels={list.map((b) => b.label)}
                series={[{ key: "r", label: "دریافتی", color: "var(--series-single)", values: bucketize(received, list, (p) => p.value) }]}
                format={formatToman}
                axisFormat={compactToman}
              />
            ) : (
              <Skeleton className="h-60" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

const STATUS_SERIES = [
  { key: "open", label: "باز", color: "var(--series-open)" },
  { key: "won", label: "فروش انجام شد", color: "var(--series-won)" },
  { key: "lost", label: "به نتیجه نرسید", color: "var(--series-lost)" },
] as const;

function InboundReport({ filters, period }: { filters: ListParams; period: Period }) {
  const [group, setGroup] = useState<"time" | "user" | "source">("time");
  const [measure, setMeasure] = useState<"count" | "amount">("count");
  const { data } = useReport<{ rows: InboundRow[]; evaluated_on: string }>("inbound-deals", { ...filters, group, measure });
  const format = measure === "amount" ? formatToman : (v: number) => formatNumber(v);

  let labels: string[] = [];
  let values: Record<"open" | "won" | "lost", number[]> = { open: [], won: [], lost: [] };
  if (data) {
    if (group === "time") {
      const list = buckets(period.from, period.to);
      const points = data.rows.map((r) => ({ date: r.key, ...r }));
      labels = list.map((b) => b.label);
      values = {
        open: bucketize(points, list, (p) => p.open),
        won: bucketize(points, list, (p) => p.won),
        lost: bucketize(points, list, (p) => p.lost),
      };
    } else {
      labels = data.rows.map((r) => r.label);
      values = { open: data.rows.map((r) => r.open), won: data.rows.map((r) => r.won), lost: data.rows.map((r) => r.lost) };
    }
  }

  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            label="محور"
            value={group}
            onChange={setGroup}
            options={[
              ["time", "زمان ثبت"],
              ["user", "کارشناس ثبت‌کننده"],
              ["source", "منبع جذب"],
            ]}
          />
          <Segmented
            label="معیار"
            value={measure}
            onChange={setMeasure}
            options={[
              ["count", "تعداد"],
              ["amount", "مبلغ"],
            ]}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          فروش‌هایی که در این بازه ثبت شده‌اند، با وضعیتشان در تاریخ {data ? formatIsoDate(data.evaluated_on) : "…"}.
          {measure === "amount" ? " مبلغ فروش انجام‌شده از قرارداد و بقیه از مبلغ تخمینی است — تومان." : ""} این گزارش با «فروش» بر
          اساس تاریخ قرارداد فرق دارد.
        </p>
      </CardHeader>
      <CardContent>
        {data ? (
          labels.length ? (
            <ColumnChart
              caption="معاملات ورودی"
              labels={labels}
              series={STATUS_SERIES.map((s) => ({ ...s, values: values[s.key] }))}
              format={format}
              axisFormat={measure === "amount" ? compactToman : format}
              height={260}
            />
          ) : (
            <p className="py-10 text-center text-sm text-muted-foreground">در این بازه فروشی ثبت نشده است.</p>
          )
        ) : (
          <Skeleton className="h-64" />
        )}
      </CardContent>
    </Card>
  );
}

function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: [T, string][];
}) {
  return (
    <div className="flex rounded-lg border bg-card p-0.5" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button
          key={v}
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn("rounded-md px-3 py-1 text-sm", value === v ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground")}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function SourcesReport({ filters }: { filters: ListParams }) {
  const { data } = useReport<{ source: string; won_count: number; won_amount: number }[]>("sales-by-source", filters);
  return (
    <Card>
      <CardHeader>
        <p className="text-xs text-muted-foreground">فروش انجام‌شده بر اساس منبع جذب مشتری و تاریخ قرارداد — تومان</p>
      </CardHeader>
      <CardContent>
        {data ? (
          <BarList
            caption="فروش به تفکیک منبع"
            rows={data.map((r) => ({ key: r.source, label: r.source, value: r.won_amount, detail: `${formatNumber(r.won_count)} قرارداد` }))}
            format={formatToman}
          />
        ) : (
          <Skeleton className="h-48" />
        )}
      </CardContent>
    </Card>
  );
}

function LostReport({ filters }: { filters: ListParams }) {
  const { data } = useReport<{ reason: string; count: number }[]>("lost-reasons", filters);
  return (
    <Card>
      <CardHeader>
        <p className="text-xs text-muted-foreground">فروش‌هایی که در این بازه «به نتیجه نرسید» بسته شدند، به تفکیک دلیل ثبت‌شده</p>
      </CardHeader>
      <CardContent>
        {data ? (
          <BarList caption="دلایل به نتیجه نرسیدن" rows={data.map((r) => ({ key: r.reason, label: r.reason, value: r.count }))} format={(v) => `${formatNumber(v)} فروش`} />
        ) : (
          <Skeleton className="h-48" />
        )}
      </CardContent>
    </Card>
  );
}

type PerformanceRow = {
  user: UserRef;
  inbound_deals: number;
  won_count: number;
  won_amount: number;
  lost_count: number;
  win_rate: number | null;
  open_pipeline: number;
  activities_done: number;
  overdue_activities: number;
};

function TeamReport({ filters }: { filters: ListParams }) {
  const { data } = useReport<PerformanceRow[]>("team", filters);
  return (
    <Card className="py-0">
      <CardContent className="px-0">
        {data ? (
          <DataTable
            caption="عملکرد کارشناسان"
            head={["کارشناس", "فروش ورودی", "فروش انجام‌شده", "مبلغ فروش", "به نتیجه نرسید", "نرخ برد", "فروش بالقوه", "فعالیت انجام‌شده", "معوق امروز"]}
            rows={data.map((r) => [
              r.user.full_name,
              formatNumber(r.inbound_deals),
              formatNumber(r.won_count),
              formatToman(r.won_amount),
              formatNumber(r.lost_count),
              percent(r.win_rate),
              formatToman(r.open_pipeline),
              formatNumber(r.activities_done),
              r.overdue_activities ? <span className="font-medium text-warning-foreground">{formatNumber(r.overdue_activities)}</span> : "۰",
            ])}
          />
        ) : (
          <Skeleton className="m-4 h-40" />
        )}
        <p className="px-4 py-3 text-xs text-muted-foreground">
          فروش ورودی به نام کارشناس هنگام ثبت، و فروش انجام‌شده به نام کارشناس هنگام بستن فروش حساب می‌شود؛ انتقال پرونده گزارش‌های
          گذشته را تغییر نمی‌دهد.
        </p>
      </CardContent>
    </Card>
  );
}
