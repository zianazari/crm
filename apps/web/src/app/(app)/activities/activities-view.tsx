"use client";

import Link from "next/link";
import { useState } from "react";
import { AlarmClock, Calendar, CalendarPlus, Clock, ListChecks, TriangleAlert } from "lucide-react";

import { ActivityItem } from "@/components/crm/activity-bits";
import { ActivityFormDialog } from "@/components/crm/activity-form-dialog";
import { Pagination } from "@/components/crm/list-parts";
import { PageHeader } from "@/components/layout/page-header";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatNumber } from "@/lib/format";
import { canManage, useActivities, useAssignableUsers, useMe, useWorkload } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS, type ActivityType } from "@/lib/types";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "overdue", label: "معوق", params: { range: "overdue" } },
  { key: "today", label: "امروز", params: { range: "today" } },
  { key: "tomorrow", label: "فردا", params: { range: "tomorrow" } },
  { key: "week", label: "تا آخر هفته", params: { range: "week" } },
  { key: "open", label: "همه کارهای باز", params: {} },
  { key: "done", label: "انجام‌شده", params: { status: "done" } },
] as const;

export function ActivitiesView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("today");
  const [type, setType] = useState<ActivityType | "">("");
  const [ownerId, setOwnerId] = useState("");
  const [page, setPage] = useState(1);
  const { data: me } = useMe();
  const { data: users = [] } = useAssignableUsers();
  const hydrated = useHydrated();
  // Role-based controls appear after hydration, so server and client markup match.
  const manager = hydrated && canManage(me?.role);
  const current = TABS.find((t) => t.key === tab)!;
  const { data, isPending, error } = useActivities({
    ...current.params,
    type,
    owner_id: ownerId || undefined,
    mine: !manager || undefined,
    page,
  });

  return (
    <>
      <PageHeader
        title="فعالیت‌ها"
        description="تماس‌ها، جلسه‌ها و پیگیری‌های همه پرونده‌ها در یک‌جا."
        actions={
          <>
            <Button variant="outline" nativeButton={false} render={<Link href="/calendar" />}>
              <Calendar aria-hidden />
              تقویم
            </Button>
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

      <WorkloadCard ownerId={ownerId || undefined} />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1 rounded-lg border bg-card p-1" role="tablist" aria-label="بازه">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => {
                setTab(t.key);
                setPage(1);
              }}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm",
                tab === t.key ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <NativeSelect aria-label="نوع فعالیت" value={type} onChange={(e) => setType(e.target.value as ActivityType | "")}>
          <NativeSelectOption value="">همه انواع</NativeSelectOption>
          {(Object.keys(ACTIVITY_TYPE_LABELS) as ActivityType[]).map((t) => (
            <NativeSelectOption key={t} value={t}>
              {ACTIVITY_TYPE_LABELS[t]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        {manager ? (
          <NativeSelect aria-label="کارشناس" value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
            <NativeSelectOption value="">همه کارشناسان</NativeSelectOption>
            {users.map((u) => (
              <NativeSelectOption key={u.id} value={u.id}>
                {u.full_name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        ) : null}
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      ) : isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            {tab === "overdue" ? "کار معوقی ندارید." : "فعالیتی در این بازه نیست."}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {data.items.map((a) => (
            <ActivityItem key={a.id} activity={a} />
          ))}
          <Pagination page={page} pageSize={data.page_size} total={data.total} onPage={setPage} />
        </div>
      )}
    </>
  );
}

function WorkloadCard({ ownerId }: { ownerId?: string }) {
  const { data } = useWorkload(ownerId);
  const hydrated = useHydrated();
  if (!data || !hydrated) return <Skeleton className="h-20" />;
  const hours = Math.floor(data.timed_minutes / 60);
  const minutes = data.timed_minutes % 60;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <Stat icon={ListChecks} label={`کارهای باز امروز${ownerId ? ` — ${data.owner.full_name}` : ""}`} value={formatNumber(data.open_count)} />
      <Stat
        icon={Clock}
        label="زمان برنامه‌ریزی‌شده امروز"
        value={hours ? `${formatNumber(hours)} ساعت ${minutes ? `و ${formatNumber(minutes)} دقیقه` : ""}` : `${formatNumber(minutes)} دقیقه`}
      />
      <Stat icon={AlarmClock} label="معوق" value={formatNumber(data.overdue_count)} warn={data.overdue_count > 0} />
      {data.overlaps.length ? (
        <Alert className="border-warning-foreground/30 bg-warning text-warning-foreground sm:col-span-3">
          <TriangleAlert aria-hidden />
          <AlertDescription className="text-warning-foreground">
            {formatNumber(data.overlaps.length)} هم‌پوشانی زمانی در برنامه امروز وجود دارد.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  warn,
}: {
  icon: typeof Clock;
  label: string;
  value: string;
  warn?: boolean;
}) {
  return (
    <Card className="py-4">
      <CardContent className="flex items-center gap-3">
        <span
          className={cn(
            "grid size-10 place-items-center rounded-lg",
            warn ? "bg-warning text-warning-foreground" : "bg-accent text-accent-foreground",
          )}
        >
          <Icon className="size-5" aria-hidden />
        </span>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-bold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
