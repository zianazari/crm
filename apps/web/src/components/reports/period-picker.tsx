"use client";

import { CalendarRange } from "lucide-react";

import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { PRESET_LABELS, presetPeriod, type Period, type PresetKey } from "@/lib/period";

const PRESETS = Object.keys(PRESET_LABELS) as PresetKey[];

/** Preset periods plus a custom Jalali range; start can't be after end. */
export function PeriodPicker({
  value,
  onChange,
  today,
}: {
  value: Period;
  onChange: (p: Period) => void;
  today: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="relative">
        <CalendarRange className="pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <NativeSelect
          aria-label="بازه زمانی"
          value={value.key}
          className="ps-8"
          onChange={(e) => {
            const key = e.target.value as PresetKey;
            onChange(key === "custom" ? { ...value, key } : presetPeriod(key, today));
          }}
        >
          {PRESETS.map((k) => (
            <NativeSelectOption key={k} value={k}>
              {PRESET_LABELS[k]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </span>
      {value.key === "custom" ? (
        <span className="flex flex-wrap items-center gap-2 text-sm">
          از
          <JalaliDateInput
            value={value.from}
            required
            onChange={(from) => from && onChange({ ...value, from, to: from > value.to ? from : value.to })}
          />
          تا
          <JalaliDateInput
            value={value.to}
            required
            onChange={(to) => to && onChange({ ...value, to, from: to < value.from ? to : value.from })}
          />
        </span>
      ) : null}
    </div>
  );
}
