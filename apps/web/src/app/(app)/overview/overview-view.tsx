"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlarmClock,
  ArrowDown,
  ArrowUp,
  Banknote,
  Building2,
  CalendarCheck,
  CalendarPlus,
  Clock,
  HandCoins,
  Tags,
  TriangleAlert,
  UserCheck,
  UserPlus,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

import { ActivityTypeIcon, NextActionPill } from "@/components/crm/activity-bits";
import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";
import { Owner } from "@/components/crm/bits";
import { UserAvatar } from "@/components/crm/user-avatar";
import { BarList, ColumnChart, compactToman } from "@/components/charts/charts";
import { formatTime } from "@/lib/jalali";
import { PageHeader } from "@/components/layout/page-header";
import { PeriodPicker } from "@/components/reports/period-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber, formatToman, formatTomanShort } from "@/lib/format";
import { bucketize, buckets, lastMonths, periodLabel, presetPeriod, previousPeriod, type Period } from "@/lib/period";
import { canManage, useActivities, useMe, useReport, type ReportSummary } from "@/lib/queries";
import type { Activity, ActivityBrief, UserRef } from "@/lib/types";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

type FollowUp = {
  deal_id: string;
  title: string;
  customer: string;
  organization: string | null;
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
  // Wait for hydration too: the user may already be cached when the page hydrates.
  const ready = useHydrated();
  if (!ready || !me || me.finance_member) return <Skeleton className="h-96" />;
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
          value={summary ? formatTomanShort(summary.sales.amount) : null}
          exact={summary ? formatToman(summary.sales.amount) : undefined}
          sub={summary ? `${formatNumber(summary.sales.count)} قرارداد` : null}
          delta={summary && before ? change(summary.sales.amount, before.sales.amount) : undefined}
        />
        <Kpi
          icon={Banknote}
          label="دریافتی"
          value={summary ? formatTomanShort(summary.received) : null}
          exact={summary ? formatToman(summary.received) : undefined}
          sub="پس از کسر بازپرداخت"
          delta={summary && before ? change(summary.received, before.received) : undefined}
        />
        <Kpi
          icon={TriangleAlert}
          label="مانده دریافت‌نشده"
          value={summary ? formatTomanShort(summary.unpaid_balance) : null}
          exact={summary ? formatToman(summary.unpaid_balance) : undefined}
          sub="همه فروش‌های انجام‌شده تا امروز"
          warn={Boolean(summary?.unpaid_balance)}
        />
        <Kpi
          icon={Tags}
          label="فروش‌های باز"
          value={summary ? formatNumber(summary.pipeline.count) : null}
          sub={summary ? `فروش بالقوه ${formatTomanShort(summary.pipeline.amount)}` : null}
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
  exact,
  sub,
  delta,
  warn,
}: {
  icon: LucideIcon;
  label: string;
  value: string | null;
  /** The exact amount behind a rounded headline, for the tooltip. */
  exact?: string;
  sub?: string | null;
  delta?: number | null;
  warn?: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <p className="text-base text-muted-foreground">{label}</p>
            {value === null ? (
              <Skeleton className="h-9 w-36" />
            ) : (
              <KpiValue value={value} exact={exact} />
            )}
          </div>
          <span
            className={cn(
              "grid size-12 shrink-0 place-items-center rounded-2xl",
              warn ? "bg-warning text-warning-foreground" : "bg-accent text-accent-foreground",
            )}
          >
            <Icon className="size-6" aria-hidden />
          </span>
        </div>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          {delta !== undefined ? <Delta value={delta} /> : null}
          {sub}
        </p>
      </CardContent>
    </Card>
  );
}

/** «۱٬۰۶۰ میلیون تومان» on one line: the number large, the unit smaller beside it. */
function KpiValue({ value, exact }: { value: string; exact?: string }) {
  const [number, ...rest] = value.split(" ");
  const unit = rest.at(-1) === "تومان" ? rest.join(" ") : "";
  return (
    <p className="flex items-baseline gap-1.5 whitespace-nowrap" title={exact}>
      <span className="text-[1.625rem] leading-tight font-extrabold tracking-tight">{unit ? number : value}</span>
      {unit ? <span className="text-base font-bold">{unit}</span> : null}
    </p>
  );
}

/** Change vs the previous period, as in the design: «↑ ۱۸٪ نسبت به دوره قبل». The arrow
 * and the word carry the direction, so it never relies on colour alone. */
function Delta({ value }: { value: number | null }) {
  if (value === null) return <span>بدون مقایسه با دوره قبل</span>;
  const up = value >= 0;
  return (
    <span className="flex items-center gap-1">
      <span className={cn("flex items-center gap-0.5 font-semibold", up ? "text-success-foreground" : "text-destructive")}>
        {up ? <ArrowUp className="size-4" aria-hidden /> : <ArrowDown className="size-4" aria-hidden />}
        {formatNumber(Math.abs(value))}٪
      </span>
      {up ? "بیشتر از" : "کمتر از"} دوره قبل
    </span>
  );
}

function MiniStat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number | undefined }) {
  return (
    <Card className="py-4">
      <CardContent className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-foreground">
          <Icon className="size-5" aria-hidden />
        </span>
        <span className="flex-1 text-base text-muted-foreground">{label}</span>
        {value === undefined ? <Skeleton className="h-7 w-10" /> : <span className="text-2xl font-extrabold">{formatNumber(value)}</span>}
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
        <p className="text-sm text-muted-foreground">مبلغ قراردادهای ثبت‌شده، به تفکیک ماه تاریخ قرارداد</p>
      </CardHeader>
      <CardContent>
        {points ? (
          <ColumnChart
            caption="روند فروش شش ماه اخیر"
            // Month names only, as in the design; the year is in the tooltip and table.
            labels={list.map((b) => b.label.split(" ")[0])}
            series={[{ key: "sales", label: "فروش", color: "var(--series-single)", values: bucketize(points, list, (p) => p.value) }]}
            format={formatToman}
            unit="میلیون تومان"
            axisFormat={(v) => formatNumber(Math.round(v / 1e6))}
            // One hue from light to dark: older months lighter, the latest darkest.
            columnColors={list.map(
              (_, i) => `color-mix(in oklch, var(--series-single) ${Math.round(55 + (45 * i) / Math.max(1, list.length - 1))}%, var(--card))`,
            )}
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
        <p className="text-sm text-muted-foreground">تعداد فروش‌ها؛ مبلغ تخمینی در کنار هر مرحله</p>
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

const ROW = "border-b last:border-b-0";

function TodayActivities() {
  const { data: me } = useMe();
  const hydrated = useHydrated();
  const team = hydrated && canManage(me?.role);
  const { data, dataUpdatedAt } = useActivities({ range: "today", mine: !team, page_size: 6 });
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <CalendarCheck className="size-6" aria-hidden />
          فعالیت‌های امروز
        </CardTitle>
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/activities" />}>
          همه فعالیت‌ها
        </Button>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-40" />
        ) : data.items.length === 0 ? (
          <p className="py-6 text-center text-base text-muted-foreground">برای امروز کاری ندارید.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-base">
              <thead>
                <tr className="bg-muted/60 text-sm text-muted-foreground">
                  <th className="rounded-s-lg px-3 py-2.5 text-start font-medium">موضوع</th>
                  <th className="px-3 py-2.5 text-start font-medium">زمان</th>
                  <th className="px-3 py-2.5 text-start font-medium">مسئول</th>
                  <th className="rounded-e-lg px-3 py-2.5 text-start font-medium">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <TodayRow key={a.id} activity={a} now={dataUpdatedAt} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TodayRow({ activity: a, now }: { activity: Activity; now: number }) {
  const done = a.status === "done";
  const late = !done && a.start_at !== null && new Date(a.start_at).getTime() < now;
  return (
    <tr className={ROW}>
      <td className="px-3 py-3">
        <Link href={a.deal ? `/deals/${a.deal.id}` : a.customer ? `/customers/${a.customer.id}` : "/activities"} className="flex items-center gap-3 hover:text-primary">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-foreground">
            <ActivityTypeIcon type={a.type} className="size-5" />
          </span>
          <span className="min-w-0">
            <span className="block truncate font-semibold">{a.title}</span>
            {a.customer ? <span className="block truncate text-sm text-muted-foreground">{a.customer.name}</span> : null}
          </span>
        </Link>
      </td>
      <td className="px-3 py-3">
        <span className="rounded-lg bg-muted px-2.5 py-1 text-sm font-medium tabular-nums">
          {a.start_at ? formatTime(a.start_at) : "بدون ساعت"}
        </span>
      </td>
      <td className="px-3 py-3">
        <Owner user={a.owner} className="text-base" />
      </td>
      <td className="px-3 py-3">
        <span
          className={cn(
            "inline-flex items-center gap-1 whitespace-nowrap rounded-lg px-2.5 py-1 text-sm font-medium",
            done ? "bg-muted text-muted-foreground" : late ? "bg-warning text-warning-foreground" : "bg-success text-success-foreground",
          )}
        >
          {late ? <AlarmClock className="size-4" aria-hidden /> : null}
          {done ? "انجام شد" : late ? "عقب‌افتاده" : "برنامه‌ریزی شده"}
        </span>
      </td>
    </tr>
  );
}

function NeedsFollowUp({ count }: { count: number | undefined }) {
  const { data: rows } = useReport<FollowUp[]>("needs-follow-up", { limit: 6 });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          <Clock className="size-6" aria-hidden />
          نیازمند پیگیری
          {count ? <span className="text-base font-normal text-muted-foreground">({formatNumber(count)} بدون اقدام بعدی)</span> : null}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!rows ? (
          <Skeleton className="h-40" />
        ) : rows.length === 0 ? (
          <p className="py-6 text-center text-base text-muted-foreground">همه فروش‌های باز پیگیری برنامه‌ریزی‌شده دارند.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[22rem] text-base">
              <thead>
                <tr className="bg-muted/60 text-sm text-muted-foreground">
                  <th className="rounded-s-lg px-3 py-2.5 text-start font-medium">مشتری</th>
                  <th className="rounded-e-lg px-3 py-2.5 text-start font-medium">موضوع</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.deal_id} className={ROW}>
                    <td className="px-3 py-3 align-top">
                      <Link href={`/deals/${r.deal_id}`} className="flex items-center gap-3 hover:text-primary">
                        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-foreground">
                          {r.organization ? <Building2 className="size-5" aria-hidden /> : <UserRound className="size-5" aria-hidden />}
                        </span>
                        <span className="min-w-0">
                          <span className="block font-semibold">{r.organization ?? r.customer}</span>
                          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                            <UserAvatar user={r.owner} className="size-5 text-[0.6rem]" />
                            {r.owner.full_name}
                          </span>
                        </span>
                      </Link>
                    </td>
                    <td className="space-y-1.5 px-3 py-3 align-top">
                      <span className="block">{r.title}</span>
                      <NextActionPill next={r.next_activity} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
