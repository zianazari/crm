const numberFormatter = new Intl.NumberFormat("fa-IR");

/** Formats a number with Persian digits and grouping, e.g. 1200000 → «۱٬۲۰۰٬۰۰۰». */
export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** Formats an amount in the organization's base currency (toman). */
export function formatToman(value: number): string {
  return `${formatNumber(value)} تومان`;
}

const persianDigits = "۰۱۲۳۴۵۶۷۸۹";
const arabicDigits = "٠١٢٣٤٥٦٧٨٩";

/** Converts Persian and Arabic-Indic digits to ASCII so OTP codes and phone numbers compare equally. */
export function toAsciiDigits(input: string): string {
  return input.replace(/[۰-۹٠-٩]/g, (ch) => {
    const p = persianDigits.indexOf(ch);
    return String(p >= 0 ? p : arabicDigits.indexOf(ch));
  });
}

const dateFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "Asia/Tehran",
  year: "numeric",
  month: "long",
  day: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
  timeZone: "Asia/Tehran",
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Jalali date in the organization's time zone, e.g. «۲۶ آبان ۱۴۰۵». */
export function formatDate(iso: string | null | undefined): string {
  return iso ? dateFormatter.format(new Date(iso)) : "—";
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFormatter.format(new Date(iso)) : "—";
}

/** «+989121234567» → «۰۹۱۲ ۱۲۳ ۴۵۶۷» for display. */
export function formatMobile(e164: string | null | undefined): string {
  if (!e164) return "—";
  const local = e164.startsWith("+98") ? `0${e164.slice(3)}` : e164;
  const grouped =
    local.length === 11 ? `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}` : local;
  return grouped.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}
