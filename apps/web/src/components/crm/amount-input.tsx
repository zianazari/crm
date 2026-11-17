"use client";

import { Input } from "@/components/ui/input";
import { formatNumber, toAsciiDigits } from "@/lib/format";

/** Whole-toman amount; shows grouped Persian digits and accepts Persian or Latin input. */
export function AmountInput({
  id,
  value,
  onChange,
  required,
}: {
  id?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  required?: boolean;
}) {
  return (
    // LTR wrapper: digits read left-to-right and the currency sits on the right.
    <div className="relative" dir="ltr">
      <Input
        id={id}
        inputMode="numeric"
        dir="ltr"
        required={required}
        value={value === null ? "" : formatNumber(value)}
        onChange={(e) => {
          const digits = toAsciiDigits(e.target.value).replace(/\D/g, "").slice(0, 15);
          onChange(digits ? Number(digits) : null);
        }}
        className="pe-14 text-start"
      />
      <span className="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
        تومان
      </span>
    </div>
  );
}
