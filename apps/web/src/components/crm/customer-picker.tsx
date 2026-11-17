"use client";

import { useState } from "react";
import { UserRound, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCustomers } from "@/lib/queries";
import type { CustomerFull } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";

/** Search the customers the user can work on (deals open only on those). */
export function CustomerPicker({
  value,
  onChange,
}: {
  value: CustomerFull | null;
  onChange: (customer: CustomerFull | null) => void;
}) {
  const [query, setQuery] = useState("");
  const search = useDebounced(query.trim());
  const { data } = useCustomers({ q: search, page_size: 10 });
  const results = (data?.items ?? []).filter((c): c is CustomerFull => c.access === "full");

  if (value) {
    return (
      <div className="flex h-9 items-center justify-between rounded-lg border bg-muted/40 px-3 text-sm">
        <span className="flex items-center gap-2">
          <UserRound className="size-4 text-muted-foreground" aria-hidden />
          {value.full_name}
        </span>
        <Button type="button" variant="ghost" size="icon-sm" aria-label="تغییر مشتری" onClick={() => onChange(null)}>
          <X />
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="نام مشتری را جست‌وجو کنید"
        aria-label="جست‌وجوی مشتری"
      />
      <ul className="max-h-44 overflow-y-auto rounded-lg border bg-popover p-1 text-sm shadow-sm">
        {results.length === 0 ? (
          <li className="px-2 py-1.5 text-muted-foreground">مشتری‌ای پیدا نشد.</li>
        ) : (
          results.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onChange(c)}
                className="w-full rounded-md px-2 py-1.5 text-start hover:bg-muted"
              >
                {c.full_name}
                {c.organizations[0] ? (
                  <span className="text-xs text-muted-foreground"> — {c.organizations[0].organization.name}</span>
                ) : null}
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
