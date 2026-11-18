import { isValidJalaaliDate, jalaaliMonthLength, toGregorian, toJalaali } from "jalaali-js";

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

const pad = (n: number) => String(n).padStart(2, "0");

/** Today's calendar date in Tehran as "YYYY-MM-DD" (Gregorian, as the API expects). */
export function todayIso(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tehran",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return parts; // en-CA formats as YYYY-MM-DD
}

export function isoToJalali(iso: string): { jy: number; jm: number; jd: number } {
  const [gy, gm, gd] = iso.split("-").map(Number);
  return toJalaali(gy, gm, gd);
}

export function jalaliToIso(jy: number, jm: number, jd: number): string | null {
  if (!isValidJalaaliDate(jy, jm, jd)) return null;
  const { gy, gm, gd } = toGregorian(jy, jm, jd);
  return `${gy}-${pad(gm)}-${pad(gd)}`;
}

export function monthLength(jy: number, jm: number): number {
  return jalaaliMonthLength(jy, jm);
}

/** A calendar date (no time) such as a contract date, shown in Jalali: «۲۰ آبان ۱۴۰۵». */
export function formatIsoDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const { jy, jm, jd } = isoToJalali(iso);
  const fa = (n: number) => n.toLocaleString("fa-IR", { useGrouping: false });
  return `${fa(jd)} ${JALALI_MONTHS[jm - 1]} ${fa(jy)}`;
}

export const WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

/** Adds days to a "YYYY-MM-DD" calendar date. */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 0 = Saturday … 6 = Friday (the Iranian week). */
export function weekdayIndex(iso: string): number {
  return (new Date(`${iso}T00:00:00Z`).getUTCDay() + 1) % 7;
}

export function startOfWeek(iso: string): string {
  return addDays(iso, -weekdayIndex(iso));
}

const timeFormatter = new Intl.DateTimeFormat("fa-IR", {
  timeZone: "Asia/Tehran",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** «۱۰:۳۰» in Tehran time. */
export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

/** Minutes after local midnight in Tehran, for placing events in the calendar grid. */
export function minutesOfDay(iso: string): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tehran",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return get("hour") * 60 + get("minute");
}

/** "HH:MM" (Latin digits, for the API) of an instant in Tehran. */
export function hhmm(iso: string): string {
  const m = minutesOfDay(iso);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

/** «امروز»، «فردا»، «دیروز» or a Jalali date. */
export function dayLabel(iso: string, today: string): string {
  if (iso === today) return "امروز";
  if (iso === addDays(today, 1)) return "فردا";
  if (iso === addDays(today, -1)) return "دیروز";
  return formatIsoDate(iso);
}
