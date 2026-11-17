"use client";

import Link from "next/link";
import { useState } from "react";
import { CalendarPlus, ChevronLeft, ChevronRight, CircleCheck, List } from "lucide-react";

import { ActivityTypeIcon, CompleteActivityDialog } from "@/components/crm/activity-bits";
import { ActivityFormDialog, type ActivityDefaults } from "@/components/crm/activity-form-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { formatNumber } from "@/lib/format";
import {
  addDays,
  formatIsoDate,
  formatTime,
  isoToJalali,
  JALALI_MONTHS,
  jalaliToIso,
  minutesOfDay,
  monthLength,
  startOfWeek,
  WEEKDAYS,
} from "@/lib/jalali";
import { canManage, useAssignableUsers, useCalendar, useMe } from "@/lib/queries";
import { ACTIVITY_TYPE_LABELS, type Activity, type ActivityType } from "@/lib/types";
import { cn } from "@/lib/utils";

type View = "week" | "day" | "month";

const HOUR_START = 7;
const HOUR_END = 22;
const HOUR_HEIGHT = 56; // px
const fa = (n: number) => n.toLocaleString("fa-IR", { useGrouping: false });

const TYPE_STYLES: Record<ActivityType, string> = {
  call: "border-s-sky-500 bg-sky-50 text-sky-950",
  meeting: "border-s-violet-500 bg-violet-50 text-violet-950",
  follow_up: "border-s-emerald-600 bg-emerald-50 text-emerald-950",
  task: "border-s-amber-500 bg-amber-50 text-amber-950",
};

function monthRange(iso: string): [string, string] {
  const { jy, jm } = isoToJalali(iso);
  return [jalaliToIso(jy, jm, 1)!, jalaliToIso(jy, jm, monthLength(jy, jm))!];
}

function shiftMonth(iso: string, delta: number): string {
  const { jy, jm } = isoToJalali(iso);
  const index = jy * 12 + (jm - 1) + delta;
  return jalaliToIso(Math.floor(index / 12), (index % 12) + 1, 1)!;
}

export function CalendarView({ today }: { today: string }) {
  const [view, setView] = useState<View>("week");
  const [anchor, setAnchor] = useState(today);
  const [type, setType] = useState<ActivityType | "">("");
  const [owner, setOwner] = useState("me");
  const [creating, setCreating] = useState<ActivityDefaults | null>(null);
  const [selected, setSelected] = useState<Activity | null>(null);
  const { data: me } = useMe();
  const { data: users = [] } = useAssignableUsers();
  const manager = canManage(me?.role);

  const [from, to] =
    view === "month" ? monthRange(anchor) : view === "day" ? [anchor, anchor] : [startOfWeek(anchor), addDays(startOfWeek(anchor), 6)];
  const { data: activities = [] } = useCalendar({
    date_from: from,
    date_to: to,
    type,
    mine: owner === "me" || undefined,
    owner_id: owner !== "me" && owner !== "all" ? owner : undefined,
  });

  function move(delta: number) {
    if (view === "month") setAnchor(shiftMonth(anchor, delta));
    else setAnchor(addDays(anchor, delta * (view === "week" ? 7 : 1)));
  }

  const { jy, jm } = isoToJalali(from);
  const title =
    view === "month"
      ? `${JALALI_MONTHS[jm - 1]} ${fa(jy)}`
      : view === "day"
        ? `${WEEKDAYS[(new Date(`${anchor}T00:00:00Z`).getUTCDay() + 1) % 7]} ${formatIsoDate(anchor)}`
        : `${formatIsoDate(from)} تا ${formatIsoDate(to)}`;

  const days = view === "day" ? [anchor] : Array.from({ length: 7 }, (_, i) => addDays(from, i));

  return (
    <>
      <PageHeader
        title="تقویم"
        description="برنامه زمانی فعالیت‌ها و جلسه‌ها. روی زمان خالی کلیک کنید تا فعالیت بسازید."
        actions={
          <>
            <Button variant="outline" nativeButton={false} render={<Link href="/activities" />}>
              <List aria-hidden />
              فهرست
            </Button>
            <Button onClick={() => setCreating({ due_date: anchor })}>
              <CalendarPlus aria-hidden />
              فعالیت جدید
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" aria-label="قبلی" onClick={() => move(-1)}>
            <ChevronRight />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setAnchor(today)}>
            امروز
          </Button>
          <Button variant="outline" size="icon-sm" aria-label="بعدی" onClick={() => move(1)}>
            <ChevronLeft />
          </Button>
        </div>
        <h2 className="min-w-48 font-semibold">{title}</h2>
        <div className="ms-auto flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border bg-card p-0.5" role="radiogroup" aria-label="نما">
            {(
              [
                ["day", "روز"],
                ["week", "هفته"],
                ["month", "ماه"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                role="radio"
                aria-checked={view === value}
                onClick={() => setView(value)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm",
                  view === value ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <NativeSelect aria-label="نوع" value={type} onChange={(e) => setType(e.target.value as ActivityType | "")}>
            <NativeSelectOption value="">همه انواع</NativeSelectOption>
            {(Object.keys(ACTIVITY_TYPE_LABELS) as ActivityType[]).map((t) => (
              <NativeSelectOption key={t} value={t}>
                {ACTIVITY_TYPE_LABELS[t]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          {manager ? (
            <NativeSelect aria-label="کارشناس" value={owner} onChange={(e) => setOwner(e.target.value)}>
              <NativeSelectOption value="me">برنامه من</NativeSelectOption>
              <NativeSelectOption value="all">همه تیم</NativeSelectOption>
              {users
                .filter((u) => u.id !== me?.id)
                .map((u) => (
                  <NativeSelectOption key={u.id} value={u.id}>
                    {u.full_name}
                  </NativeSelectOption>
                ))}
            </NativeSelect>
          ) : null}
        </div>
      </div>

      <Card className="gap-0 overflow-hidden py-0">
        {view === "month" ? (
          <MonthGrid
            anchor={anchor}
            today={today}
            activities={activities}
            onOpenDay={(day) => {
              setAnchor(day);
              setView("day");
            }}
            onSelect={setSelected}
          />
        ) : (
          <TimeGrid
            days={days}
            today={today}
            activities={activities}
            onCreate={setCreating}
            onSelect={setSelected}
          />
        )}
      </Card>

      {creating ? (
        <ActivityFormDialog
          key={JSON.stringify(creating)}
          open
          defaults={creating}
          onOpenChange={(open) => !open && setCreating(null)}
        />
      ) : null}
      {selected && (selected.status === "pending" || selected.status === "in_progress") ? (
        <CompleteActivityDialog activity={selected} onClose={() => setSelected(null)} />
      ) : null}
    </>
  );
}

function EventChip({ activity, onSelect, compact }: { activity: Activity; onSelect: (a: Activity) => void; compact?: boolean }) {
  const done = activity.status === "done";
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onSelect(activity);
      }}
      className={cn(
        "flex w-full min-w-0 items-center gap-1 rounded-md border-s-4 px-1.5 py-0.5 text-start text-xs",
        TYPE_STYLES[activity.type],
        done && "opacity-60",
        activity.overdue && "ring-1 ring-warning-foreground/50",
      )}
      title={`${ACTIVITY_TYPE_LABELS[activity.type]}: ${activity.title} — ${activity.owner.full_name}`}
    >
      {done ? <CircleCheck className="size-3 shrink-0" aria-label="انجام‌شده" /> : <ActivityTypeIcon type={activity.type} className="size-3 shrink-0" />}
      {!compact && activity.start_at ? <span className="shrink-0">{formatTime(activity.start_at)}</span> : null}
      <span className={cn("truncate", done && "line-through")}>{activity.title}</span>
    </button>
  );
}

/** Week / day view: an "all day" row for date-only activities above an hourly grid. */
function TimeGrid({
  days,
  today,
  activities,
  onCreate,
  onSelect,
}: {
  days: string[];
  today: string;
  activities: Activity[];
  onCreate: (d: ActivityDefaults) => void;
  onSelect: (a: Activity) => void;
}) {
  const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);
  const cols = `4rem repeat(${days.length}, minmax(7rem, 1fr))`;
  const now = new Date();
  const nowIso = now.toISOString();
  const nowMinutes = minutesOfDay(nowIso);

  return (
    <div className="overflow-x-auto">
      <div style={{ gridTemplateColumns: cols }} className="grid min-w-fit">
        {/* Header */}
        <div className="border-b bg-muted/40" />
        {days.map((day) => (
          <div
            key={day}
            className={cn("border-b border-s bg-muted/40 px-2 py-2 text-center text-sm", day === today && "bg-accent text-accent-foreground")}
          >
            <div className="text-xs text-muted-foreground">{WEEKDAYS[(new Date(`${day}T00:00:00Z`).getUTCDay() + 1) % 7]}</div>
            <div className="font-semibold">{fa(isoToJalali(day).jd)}</div>
          </div>
        ))}

        {/* Date-only activities: never occupy a time slot. */}
        <div className="flex items-center justify-center border-b px-1 text-center text-[11px] text-muted-foreground">بدون ساعت</div>
        {days.map((day) => (
          <div
            key={day}
            role="button"
            tabIndex={0}
            aria-label={`فعالیت بدون ساعت در ${formatIsoDate(day)}`}
            onClick={() => onCreate({ due_date: day, start_time: null })}
            onKeyDown={(e) => e.key === "Enter" && onCreate({ due_date: day, start_time: null })}
            className="min-h-10 space-y-1 border-b border-s p-1 hover:bg-muted/40"
          >
            {activities
              .filter((a) => a.due_date === day && !a.start_at)
              .map((a) => (
                <EventChip key={a.id} activity={a} onSelect={onSelect} compact />
              ))}
          </div>
        ))}

        {/* Hours */}
        <div className="relative">
          {hours.map((h) => (
            <div key={h} style={{ height: HOUR_HEIGHT }} className="border-b pe-2 pt-1 text-end text-xs text-muted-foreground">
              {fa(h)}:۰۰
            </div>
          ))}
        </div>
        {days.map((day) => {
          const timed = activities.filter((a) => a.due_date === day && a.start_at);
          const lanes = assignLanes(timed);
          return (
            <div key={day} className="relative border-s">
              {hours.map((h) =>
                [0, 30].map((m) => {
                  const time = `${String(h).padStart(2, "0")}:${m === 0 ? "00" : "30"}`;
                  return (
                    <button
                      key={time}
                      type="button"
                      aria-label={`فعالیت جدید ${formatIsoDate(day)} ساعت ${fa(h)}:${m === 0 ? "۰۰" : "۳۰"}`}
                      onClick={() => onCreate({ due_date: day, start_time: time, duration_minutes: 30 })}
                      style={{ height: HOUR_HEIGHT / 2 }}
                      className={cn("block w-full hover:bg-accent/50", m === 30 ? "border-b" : "border-b border-dashed border-border/60")}
                    />
                  );
                }),
              )}
              {timed.map((a) => {
                const start = minutesOfDay(a.start_at!);
                const top = ((start - HOUR_START * 60) / 60) * HOUR_HEIGHT;
                const height = (Math.max(a.duration_minutes ?? 30, 20) / 60) * HOUR_HEIGHT;
                const { lane, of } = lanes.get(a.id)!;
                if (top + height < 0 || top > hours.length * HOUR_HEIGHT) return null;
                return (
                  <div
                    key={a.id}
                    className="absolute px-0.5"
                    style={{
                      top: Math.max(top, 0),
                      height,
                      insetInlineStart: `${(lane / of) * 100}%`,
                      width: `${100 / of}%`,
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => onSelect(a)}
                      className={cn(
                        "flex h-full w-full flex-col overflow-hidden rounded-md border-s-4 px-1.5 py-1 text-start text-xs shadow-xs",
                        TYPE_STYLES[a.type],
                        a.status === "done" && "opacity-60",
                      )}
                    >
                      <span className="flex items-center gap-1 font-medium">
                        {a.status === "done" ? <CircleCheck className="size-3" aria-label="انجام‌شده" /> : <ActivityTypeIcon type={a.type} className="size-3" />}
                        <span className={cn("truncate", a.status === "done" && "line-through")}>{a.title}</span>
                      </span>
                      <span className="truncate opacity-80">
                        {formatTime(a.start_at!)}
                        {a.duration_minutes ? ` · ${formatNumber(a.duration_minutes)} دقیقه` : ""}
                      </span>
                    </button>
                  </div>
                );
              })}
              {day === today && nowMinutes >= HOUR_START * 60 && nowMinutes < HOUR_END * 60 ? (
                <div
                  className="pointer-events-none absolute inset-x-0 border-t-2 border-destructive"
                  style={{ top: ((nowMinutes - HOUR_START * 60) / 60) * HOUR_HEIGHT }}
                  aria-label="اکنون"
                >
                  <span className="absolute -top-1.5 -start-1 size-2.5 rounded-full bg-destructive" />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Side-by-side lanes for overlapping timed activities within a day. */
function assignLanes(items: Activity[]): Map<string, { lane: number; of: number }> {
  const sorted = [...items].sort((a, b) => minutesOfDay(a.start_at!) - minutesOfDay(b.start_at!));
  const result = new Map<string, { lane: number; of: number }>();
  let group: { id: string; end: number; lane: number }[] = [];
  let groupEnd = -1;
  const flush = () => {
    const of = Math.max(1, ...group.map((g) => g.lane + 1));
    for (const g of group) result.set(g.id, { lane: g.lane, of });
    group = [];
  };
  for (const a of sorted) {
    const start = minutesOfDay(a.start_at!);
    const end = start + (a.duration_minutes ?? 30);
    if (start >= groupEnd) {
      flush();
      groupEnd = -1;
    }
    const used = new Set(group.filter((g) => g.end > start).map((g) => g.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    group.push({ id: a.id, end, lane });
    groupEnd = Math.max(groupEnd, end);
  }
  flush();
  return result;
}

function MonthGrid({
  anchor,
  today,
  activities,
  onOpenDay,
  onSelect,
}: {
  anchor: string;
  today: string;
  activities: Activity[];
  onOpenDay: (day: string) => void;
  onSelect: (a: Activity) => void;
}) {
  const [first, last] = monthRange(anchor);
  const gridStart = startOfWeek(first);
  const weeks = Math.ceil(((new Date(`${last}T00:00:00Z`).getTime() - new Date(`${gridStart}T00:00:00Z`).getTime()) / 86_400_000 + 1) / 7);
  const cells = Array.from({ length: weeks * 7 }, (_, i) => addDays(gridStart, i));
  const { jm } = isoToJalali(first);

  return (
    <div className="grid grid-cols-7">
      {WEEKDAYS.map((d) => (
        <div key={d} className="border-b bg-muted/40 py-2 text-center text-xs font-medium text-muted-foreground">
          {d}
        </div>
      ))}
      {cells.map((day) => {
        const inMonth = isoToJalali(day).jm === jm;
        const items = activities.filter((a) => a.due_date === day);
        return (
          <div
            key={day}
            role="button"
            tabIndex={0}
            onClick={() => onOpenDay(day)}
            onKeyDown={(e) => e.key === "Enter" && onOpenDay(day)}
            aria-label={`${formatIsoDate(day)} — ${formatNumber(items.length)} فعالیت`}
            className={cn(
              "min-h-24 space-y-1 border-b border-s p-1.5 text-start hover:bg-muted/40",
              !inMonth && "bg-muted/20 text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "inline-grid size-6 place-items-center rounded-full text-xs",
                day === today && "bg-primary font-semibold text-primary-foreground",
              )}
            >
              {fa(isoToJalali(day).jd)}
            </span>
            {items.slice(0, 3).map((a) => (
              <EventChip key={a.id} activity={a} onSelect={onSelect} />
            ))}
            {items.length > 3 ? (
              <p className="text-[11px] text-muted-foreground">{formatNumber(items.length - 3)} مورد دیگر</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
