/** Report periods in the Jalali calendar (spec 4.4: "this/last week, month, year and a
 * custom range, in the organization's calendar and time zone"). Dates are Gregorian
 * "YYYY-MM-DD" strings, which is what the API takes. */

import {
  addDays,
  formatIsoDate,
  isoToJalali,
  JALALI_MONTHS,
  jalaliToIso,
  monthLength,
  startOfWeek,
} from "@/lib/jalali";

export type PresetKey =
  | "this_week"
  | "last_week"
  | "this_month"
  | "last_month"
  | "last_3_months"
  | "this_year"
  | "last_year"
  | "custom";

export type Period = { key: PresetKey; from: string; to: string };

export const PRESET_LABELS: Record<PresetKey, string> = {
  this_week: "هفته جاری",
  last_week: "هفته گذشته",
  this_month: "ماه جاری",
  last_month: "ماه گذشته",
  // Explicitly the last three months up to today, not "the month three months ago".
  last_3_months: "سه ماه اخیر",
  this_year: "سال جاری",
  last_year: "سال گذشته",
  custom: "بازه دلخواه",
};

function monthBounds(jy: number, jm: number): [string, string] {
  return [jalaliToIso(jy, jm, 1)!, jalaliToIso(jy, jm, monthLength(jy, jm))!];
}

function shiftMonth(jy: number, jm: number, delta: number): [number, number] {
  const index = jy * 12 + (jm - 1) + delta;
  return [Math.floor(index / 12), (index % 12) + 1];
}

export function presetPeriod(key: Exclude<PresetKey, "custom">, today: string): Period {
  const { jy, jm } = isoToJalali(today);
  switch (key) {
    case "this_week": {
      const start = startOfWeek(today);
      return { key, from: start, to: addDays(start, 6) };
    }
    case "last_week": {
      const start = addDays(startOfWeek(today), -7);
      return { key, from: start, to: addDays(start, 6) };
    }
    case "this_month": {
      const [from, to] = monthBounds(jy, jm);
      return { key, from, to };
    }
    case "last_month": {
      const [py, pm] = shiftMonth(jy, jm, -1);
      const [from, to] = monthBounds(py, pm);
      return { key, from, to };
    }
    case "last_3_months":
      return { key, from: addDays(today, -89), to: today };
    case "this_year":
      return { key, from: jalaliToIso(jy, 1, 1)!, to: jalaliToIso(jy, 12, monthLength(jy, 12))! };
    case "last_year":
      return { key, from: jalaliToIso(jy - 1, 1, 1)!, to: jalaliToIso(jy - 1, 12, monthLength(jy - 1, 12))! };
  }
}

/** The comparison period: the previous calendar unit for presets, else the same length just before. */
export function previousPeriod(period: Period): Period {
  const { jy, jm } = isoToJalali(period.from);
  if (period.key === "this_month" || period.key === "last_month") {
    const [py, pm] = shiftMonth(jy, jm, -1);
    const [from, to] = monthBounds(py, pm);
    return { key: "custom", from, to };
  }
  if (period.key === "this_year" || period.key === "last_year") {
    return { key: "custom", from: jalaliToIso(jy - 1, 1, 1)!, to: jalaliToIso(jy - 1, 12, monthLength(jy - 1, 12))! };
  }
  const days = daysBetween(period.from, period.to) + 1;
  return { key: "custom", from: addDays(period.from, -days), to: addDays(period.from, -1) };
}

export function daysBetween(a: string, b: string): number {
  return Math.round((new Date(`${b}T00:00:00Z`).getTime() - new Date(`${a}T00:00:00Z`).getTime()) / 86_400_000);
}

export function periodLabel(period: Period): string {
  if (period.key !== "custom") return PRESET_LABELS[period.key];
  return `${formatIsoDate(period.from)} تا ${formatIsoDate(period.to)}`;
}

export type Bucket = { key: string; label: string; from: string; to: string };

/** Buckets for a time axis: days up to a month, weeks up to ~3 months, else Jalali months. */
export function buckets(from: string, to: string): Bucket[] {
  const span = daysBetween(from, to) + 1;
  const result: Bucket[] = [];
  const fa = (n: number) => n.toLocaleString("fa-IR", { useGrouping: false });
  if (span <= 31) {
    for (let d = from; d <= to; d = addDays(d, 1)) {
      const { jd, jm } = isoToJalali(d);
      result.push({ key: d, label: `${fa(jd)} ${JALALI_MONTHS[jm - 1]}`, from: d, to: d });
    }
  } else if (span <= 100) {
    for (let d = startOfWeek(from); d <= to; d = addDays(d, 7)) {
      const start = d < from ? from : d;
      const end = addDays(d, 6) > to ? to : addDays(d, 6);
      const { jd, jm } = isoToJalali(start);
      result.push({ key: start, label: `هفته ${fa(jd)} ${JALALI_MONTHS[jm - 1]}`, from: start, to: end });
    }
  } else {
    let { jy, jm } = isoToJalali(from);
    for (;;) {
      const [start, end] = monthBounds(jy, jm);
      if (start > to) break;
      result.push({
        key: start,
        label: `${JALALI_MONTHS[jm - 1]} ${fa(jy % 100).padStart(2, "۰")}`,
        from: start < from ? from : start,
        to: end > to ? to : end,
      });
      [jy, jm] = shiftMonth(jy, jm, 1);
    }
  }
  return result;
}

/** Sums daily points into the buckets. */
export function bucketize<T extends { date: string }>(
  points: T[],
  list: Bucket[],
  value: (p: T) => number,
): number[] {
  return list.map((b) => points.filter((p) => p.date >= b.from && p.date <= b.to).reduce((s, p) => s + value(p), 0));
}

/** The last ``n`` Jalali months ending with the month of ``today``. */
export function lastMonths(today: string, n: number): { from: string; to: string } {
  const { jy, jm } = isoToJalali(today);
  const [sy, sm] = shiftMonth(jy, jm, -(n - 1));
  return { from: monthBounds(sy, sm)[0], to: monthBounds(jy, jm)[1] };
}
