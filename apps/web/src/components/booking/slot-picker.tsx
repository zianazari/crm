"use client";

import { useState } from "react";
import { CalendarX2 } from "lucide-react";

import { isoToJalali, JALALI_MONTHS, WEEKDAYS, weekdayIndex, formatTime } from "@/lib/jalali";
import type { Slots } from "@/lib/booking";
import { cn } from "@/lib/utils";

const fa = (n: number) => n.toLocaleString("fa-IR", { useGrouping: false });

function shortDate(iso: string): string {
  const { jm, jd } = isoToJalali(iso);
  return `${fa(jd)} ${JALALI_MONTHS[jm - 1]}`;
}

/** Choose a day, then a free start time. Times are Tehran time, said so on screen. */
export function SlotPicker({
  slots,
  value,
  onChange,
  current,
}: {
  slots: Slots;
  value: string | null;
  onChange: (slot: string) => void;
  /** The time already booked, when moving a booking. */
  current?: string;
}) {
  const days = slots.days.filter((d) => d.slots.length > 0);
  const [day, setDay] = useState<string | null>(null);
  const selectedDay =
    days.find((d) => d.date === day) ?? days.find((d) => value !== null && d.slots.includes(value)) ?? days[0];

  if (days.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-10 text-center text-sm text-muted-foreground">
        <CalendarX2 className="size-7" aria-hidden />
        فعلاً زمان آزادی نیست. کمی بعد دوباره سر بزنید یا با کارشناس تماس بگیرید.
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      <div role="tablist" aria-label="روز" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
        {days.map((d) => {
          const active = d.date === selectedDay.date;
          return (
            <button
              key={d.date}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setDay(d.date)}
              className={cn(
                "flex min-w-20 shrink-0 flex-col items-center rounded-lg border px-3 py-2 text-sm transition-colors",
                active ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted",
              )}
            >
              <span className="text-xs opacity-80">{WEEKDAYS[weekdayIndex(d.date)]}</span>
              <span className="font-medium">{shortDate(d.date)}</span>
            </button>
          );
        })}
      </div>
      <div role="radiogroup" aria-label={`ساعت‌های آزاد ${WEEKDAYS[weekdayIndex(selectedDay.date)]} ${shortDate(selectedDay.date)}`} className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        {selectedDay.slots.map((slot) => {
          const checked = slot === value;
          return (
            <button
              key={slot}
              type="button"
              role="radio"
              aria-checked={checked}
              onClick={() => onChange(slot)}
              className={cn(
                "rounded-md border px-2 py-2 text-sm tabular-nums transition-colors",
                checked ? "border-primary bg-accent font-semibold text-accent-foreground ring-1 ring-primary" : "bg-card hover:bg-muted",
              )}
            >
              {formatTime(slot)}
              {slot === current ? <span className="block text-[11px] text-muted-foreground">زمان فعلی</span> : null}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">همه ساعت‌ها به وقت تهران است.</p>
    </div>
  );
}

/** «یکشنبه ۱ آذر، ساعت ۱۰:۰۰ تا ۱۰:۳۰». */
export function formatSlot(start: string, end?: string): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tehran" }).format(new Date(start));
  return `${WEEKDAYS[weekdayIndex(day)]} ${shortDate(day)}، ساعت ${formatTime(start)}${end ? ` تا ${formatTime(end)}` : ""}`;
}
