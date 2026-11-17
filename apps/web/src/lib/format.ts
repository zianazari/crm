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
