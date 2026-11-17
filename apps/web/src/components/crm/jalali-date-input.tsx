"use client";

import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { isoToJalali, JALALI_MONTHS, jalaliToIso, monthLength, todayIso } from "@/lib/jalali";

const fa = (n: number) => n.toLocaleString("fa-IR", { useGrouping: false });

/**
 * Jalali date picker built from day / month / year selects (keyboard and screen-reader
 * friendly). Value and onChange use Gregorian "YYYY-MM-DD", which is what the API stores.
 */
export function JalaliDateInput({
  id,
  value,
  onChange,
  required,
}: {
  id?: string;
  value: string | null;
  onChange: (iso: string | null) => void;
  required?: boolean;
}) {
  const current = isoToJalali(value ?? todayIso());
  const thisYear = isoToJalali(todayIso()).jy;
  const years = Array.from({ length: 9 }, (_, i) => thisYear - 5 + i);
  const days = monthLength(current.jy, current.jm);

  function update(next: Partial<{ jy: number; jm: number; jd: number }>) {
    const merged = { ...current, ...next };
    merged.jd = Math.min(merged.jd, monthLength(merged.jy, merged.jm));
    onChange(jalaliToIso(merged.jy, merged.jm, merged.jd));
  }

  if (!value) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          id={id}
          onClick={() => onChange(todayIso())}
          className="h-9 w-full rounded-lg border border-dashed px-3 text-start text-sm text-muted-foreground hover:bg-muted"
        >
          {required ? "انتخاب تاریخ" : "بدون تاریخ — انتخاب"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex gap-1.5" role="group" aria-label="تاریخ">
      <NativeSelect
        id={id}
        aria-label="روز"
        value={current.jd}
        onChange={(e) => update({ jd: Number(e.target.value) })}
      >
        {Array.from({ length: days }, (_, i) => i + 1).map((d) => (
          <NativeSelectOption key={d} value={d}>
            {fa(d)}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <NativeSelect aria-label="ماه" value={current.jm} onChange={(e) => update({ jm: Number(e.target.value) })}>
        {JALALI_MONTHS.map((name, i) => (
          <NativeSelectOption key={name} value={i + 1}>
            {name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      <NativeSelect aria-label="سال" value={current.jy} onChange={(e) => update({ jy: Number(e.target.value) })}>
        {years.map((y) => (
          <NativeSelectOption key={y} value={y}>
            {fa(y)}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      {!required ? (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="px-2 text-xs text-muted-foreground hover:text-foreground"
        >
          حذف
        </button>
      ) : null}
    </div>
  );
}
