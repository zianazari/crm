"use client";

import { useState } from "react";
import { Building2, Plus, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useOrganizations } from "@/lib/queries";
import type { Organization, Ref } from "@/lib/types";

/** Pick an existing organization by name, or create it on the spot. */
export function OrganizationPicker({
  value,
  onChange,
}: {
  value: Ref | null;
  onChange: (organization: Ref | null) => void;
}) {
  const [query, setQuery] = useState("");
  const queryClient = useQueryClient();
  const { data } = useOrganizations(query.trim());
  const results = query.trim() ? (data?.items ?? []) : [];
  const exact = results.some((o) => o.name === query.trim());

  async function create() {
    const organization = await apiFetch<Organization>("/organizations", {
      method: "POST",
      body: JSON.stringify({ name: query.trim() }),
    });
    await queryClient.invalidateQueries({ queryKey: ["organizations"] });
    onChange({ id: organization.id, name: organization.name });
    setQuery("");
  }

  if (value) {
    return (
      <div className="flex h-9 items-center justify-between rounded-lg border bg-muted/40 px-3 text-sm">
        <span className="flex items-center gap-2">
          <Building2 className="size-4 text-muted-foreground" aria-hidden />
          {value.name}
        </span>
        <Button type="button" variant="ghost" size="icon-sm" aria-label="حذف سازمان" onClick={() => onChange(null)}>
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
        placeholder="نام سازمان را جست‌وجو کنید"
        aria-label="جست‌وجوی سازمان"
      />
      {query.trim() ? (
        <ul className="max-h-40 overflow-y-auto rounded-lg border bg-popover p-1 text-sm shadow-sm">
          {results.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                onClick={() => {
                  onChange({ id: o.id, name: o.name });
                  setQuery("");
                }}
                className="w-full rounded-md px-2 py-1.5 text-start hover:bg-muted"
              >
                {o.name}
              </button>
            </li>
          ))}
          {!exact ? (
            <li>
              <button
                type="button"
                onClick={() => void create()}
                className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-start text-primary hover:bg-muted"
              >
                <Plus className="size-4" aria-hidden />
                ساخت سازمان «{query.trim()}»
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
