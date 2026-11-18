"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowDown,
  ArrowUp,
  Banknote,
  CalendarCheck,
  CalendarPlus,
  Clock,
  HandCoins,
  Tags,
  TriangleAlert,
  UserCheck,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";

import { ActivityItem, NextActionPill } from "@/components/crm/activity-bits";
import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";
import { Owner } from "@/components/crm/bits";
import { BarList, ColumnChart, compactToman } from "@/components/charts/charts";
import { PageHeader } from "@/components/layout/page-header";
import { PeriodPicker } from "@/components/reports/period-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber, formatToman } from "@/lib/format";
import { bucketize, buckets, lastMonths, periodLabel, presetPeriod, previousPeriod, type Period } from "@/lib/period";
import { useActivities, useMe, useReport, type ReportSummary } from "@/lib/queries";
import type { ActivityBrief, UserRef } from "@/lib/types";
import { cn } from "@/lib/utils";

type FollowUp = {
  deal_id: string;
  title: string;
  customer: string;
  owner: UserRef;
  reason: "no_next_action" | "overdue";
  next_activity: ActivityBrief | null;
};

/** Finance team members have no sales overview; their home is their activities. */
export function OverviewView({ today }: { today: string }) {
  const router = useRouter();
  const { data: me } = useMe();
  useEffect(() => {
    if (me?.finance_member) router.replace("/activities");
  }, [me, router]);
  if (!me || me.finance_member) return <Skeleton className="h-96" />;
  return <SalesOverview today={today} />;
}

function SalesOverview({ today }: { today: string }) {
  const [period, setPeriod] = useState<Period>(() => presetPeriod("this_month", today));
  const previous = previousPeriod(period);
  const range = { date_from: period.from, date_to: period.to };
  const { data: summary } = useReport<ReportSummary>("summary", range);
  const { data: before } = useReport<ReportSummary>("summary", { date_from: previous.from, date_to: previous.to });

  return (
    <>
      <PageHeader
        title="نمای کلی"
        description={`خلاصه فروش و کارها — ${periodLabel(period)}`}
        actions={
          <>
            <PeriodPicker value={period} onChange={setPeriod} today={today} />
            <ActivityFormDialog
              trigger={
                <Button>
                  <CalendarPlus aria-hidden />
                  فعالیت جدید
                </Button>
              }
            />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          icon={HandCoins}
          label="فروش (قرارداد)"
          value={summary ? formatToman(summary.sales.amount) : null}
          sub={summary ? `${formatNumber(summary.sales.count)} قرارداد` : null}
          delta={summary && before ? change(summary.sales.amount, before.sales.amount) : undefined}
        />
        <Kpi
          icon={Banknote}
          label="دریافتی"
          value={summary ? formatToman(summary.received) : null}
          sub="پس از کسر بازپرداخت"
          delta={summary && before ? change(summary.received, before.received) : undefined}
        />
        <Kpi
          icon={TriangleAlert}
          label="مانده دریافت‌نشده"
          value={summary ? formatToman(summary.unpaid_balance) : null}
          sub="همه فروش‌های انجام‌شده تا امروز"
          warn={Boolean(summary?.unpaid_balance)}
        />
        <Kpi
          icon={Tags}
          label="فروش‌های باز"
          value={summary ? formatNumber(summary.pipeline.count) : null}
          sub={summary ? `فروش بالقوه ${formatToman(summary.pipeline.amount)}` : null}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <MiniStat icon={UserPlus} label="مشتریان احتمالی جدید" value={summary?.new_leads} />
        <MiniStat icon={Users} label="پرونده‌های مشتری جدید" value={summary?.new_customers} />
        <MiniStat icon={UserCheck} label="مشتریان با اولین خرید" value={summary?.first_purchase_customers} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <SalesTrend today={today} />
        <StageDistribution />
      </div>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <TodayActivities />
        <NeedsFollowUp count={summary?.deals_without_next_action} />
      </div>
    </>
  );
}

function change(current: number, previous: number): number | null {
  if (!previous) return null;
  return Math.round(((current - previous) / previous) * 100);
}

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
  delta,
  warn,
}: {
  icon: LucideIcon;
  label: string;
  value: string | null;
  sub?: string | null;
  delta?: number | null;
  warn?: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">{label}</p>
            {value === null ? <Skeleton className="h-7 w-32" /> : <p className="text-2xl font-bold">{value}</p>}
          </div>
          <span
            className={cn(
              "grid size-11 shrink-0 place-items-center rounded-xl",
              warn ? "bg-warning text-warning-foreground" : "bg-accent text-accent-foreground",
            )}
          >
            <Icon className="size-5" aria-hidden />
          </span>
        </div>
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {delta !== undefined ? <Delta value={delta} /> : null}
          {sub}
        </p>
      </CardContent>
    </Card>
  );
}

/** Change vs the previous period, in words and an arrow, not colour alone. */
function Delta({ value }: { value: number | null }) {
  if (value === null) return <span>بدون مقایسه با دوره قبل</span>;
  const up = value >= 0;
  return (
    <span className={cn("flex items-center gap-0.5 font-medium", up ? "text-success-foreground" : "text-destructive")}>
      {up ? <ArrowUp className="size-3.5" aria-hidden /> : <ArrowDown className="size-3.5" aria-hidden />}
      {formatNumber(Math.abs(value))}٪ {up ? "بیشتر" : "کمتر"} از دوره قبل
    </span>
  );
}

function MiniStat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number | undefined }) {
  return (
    <Card className="py-4">
      <CardContent className="flex items-center gap-3">
        <Icon className="size-5 text-muted-foreground" aria-hidden />
        <span className="flex-1 text-sm text-muted-foreground">{label}</span>
        {value === undefined ? <Skeleton className="h-6 w-10" /> : <span className="text-lg font-bold">{formatNumber(value)}</span>}
      </CardContent>
    </Card>
  );
}

function SalesTrend({ today }: { today: string }) {
  const range = lastMonths(today, 6);
  const { data: points } = useReport<{ date: string; value: number }[]>("series", {
    metric: "sales_amount",
    date_from: range.from,
    date_to: range.to,
  });
  const list = buckets(range.from, range.to);
  return (
    <Card>
      <CardHeader>
        <CardTitle>روند فروش</CardTitle>
        <p className="text-xs text-muted-foreground">مبلغ قراردادهای ثبت‌شده، به تفکیک ماه تاریخ قرارداد — تومان</p>
      </CardHeader>
      <CardContent>
        {points ? (
          <ColumnChart
            caption="روند فروش شش ماه اخیر"
            labels={list.map((b) => b.label)}
            series={[{ key: "sales", label: "فروش", color: "var(--series-single)", values: bucketize(points, list, (p) => p.value) }]}
            format={formatToman}
            axisFormat={compactToman}
          />
        ) : (
          <Skeleton className="h-60" />
        )}
      </CardContent>
    </Card>
  );
}

function StageDistribution() {
  const { data: rows } = useReport<{ stage_id: string; stage: string; count: number; amount: number }[]>("pipeline", {});
  return (
    <Card>
      <CardHeader>
        <CardTitle>فروش‌های باز به تفکیک مرحله</CardTitle>
        <p className="text-xs text-muted-foreground">تعداد فروش‌ها؛ مبلغ تخمینی در کنار هر مرحله</p>
      </CardHeader>
      <CardContent>
        {rows ? (
          <BarList
            caption="فروش‌های باز به تفکیک مرحله"
            rows={rows.map((r) => ({ key: r.stage_id, label: r.stage, value: r.count, detail: compactToman(r.amount) }))}
            format={(v) => `${formatNumber(v)} فروش`}
          />
        ) : (
          <Skeleton className="h-48" />
        )}
      </CardContent>
    </Card>
  );
}

function TodayActivities() {
  const { data } = useActivities({ range: "today", mine: true, page_size: 6 });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <CalendarCheck className="size-5" aria-hidden />
          فعالیت‌های امروز
        </CardTitle>
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/activities" />}>
          همه فعالیت‌ها
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {!data ? (
          <Skeleton className="h-40" />
        ) : data.items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">برای امروز کاری ندارید.</p>
        ) : (
          data.items.map((a) => <ActivityItem key={a.id} activity={a} />)
        )}
      </CardContent>
    </Card>
  );
}

function NeedsFollowUp({ count }: { count: number | undefined }) {
  const { data: rows } = useReport<FollowUp[]>("needs-follow-up", { limit: 6 });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="size-5" aria-hidden />
          نیازمند پیگیری
          {count ? <span className="text-sm font-normal text-muted-foreground">({formatNumber(count)} بدون اقدام بعدی)</span> : null}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!rows ? (
          <Skeleton className="h-40" />
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">همه فروش‌های باز پیگیری برنامه‌ریزی‌شده دارند.</p>
        ) : (
          <ul className="divide-y">
            {rows.map((r) => (
              <li key={r.deal_id}>
                <Link href={`/deals/${r.deal_id}`} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm hover:text-primary">
                  <span className="min-w-0">
                    <span className="block font-medium">{r.customer}</span>
                    <span className="block truncate text-xs text-muted-foreground">{r.title}</span>
                  </span>
                  <span className="flex flex-col items-end gap-1">
                    <NextActionPill next={r.next_activity} />
                    <Owner user={r.owner} className="text-xs text-muted-foreground" />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}


