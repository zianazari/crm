"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";

import { JalaliDateInput } from "@/components/crm/jalali-date-input";
import { SearchInput } from "@/components/crm/list-parts";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Audience, ContactRef, SegmentFilters } from "@/lib/campaigns";
import { formatMobile } from "@/lib/format";
import { todayIso } from "@/lib/jalali";
import { toQuery, useAssignableUsers, useSources, useTags } from "@/lib/queries";
import { LEAD_STATUS_LABELS, type LeadStatus, type Page } from "@/lib/types";
import { useDebounced } from "@/lib/use-debounced";
import { cn } from "@/lib/utils";

function Checks<T extends string>({
  legend,
  options,
  value,
  onChange,
  empty,
}: {
  legend: string;
  options: { value: T; label: string }[];
  value: T[];
  onChange: (next: T[]) => void;
  empty?: string;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">{legend}</legend>
      {options.length === 0 ? (
        <p className="text-xs text-muted-foreground">موردی تعریف نشده است.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {options.map((o) => {
            const on = value.includes(o.value);
            return (
              <button
                key={o.value}
                type="button"
                aria-pressed={on}
                onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
                  on && "border-primary bg-accent font-medium text-accent-foreground",
                )}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      )}
      {empty && value.length === 0 ? <p className="text-xs text-muted-foreground">{empty}</p> : null}
    </fieldset>
  );
}

/** Who the campaign is for: a filtered segment or chosen contacts (spec 4.5). Only
 * records in the author's scope ever count; the API applies that. */
export function AudienceEditor({ value, onChange }: { value: Audience; onChange: (next: Audience) => void }) {
  return (
    <div className="space-y-4">
      <div role="radiogroup" aria-label="نوع مخاطبان" className="grid gap-2 sm:grid-cols-2">
        {(
          [
            ["segment", "بخشی از مخاطبان", "با فیلتر منبع، برچسب، وضعیت، مسئول و تاریخ ثبت"],
            ["selected", "مخاطبان انتخابی", "یک یا چند مشتری یا مشتری احتمالی مشخص"],
          ] as const
        ).map(([kind, title, hint]) => (
          <button
            key={kind}
            type="button"
            role="radio"
            aria-checked={value.kind === kind}
            onClick={() => onChange({ ...value, kind })}
            className={cn(
              "rounded-lg border p-3 text-start hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring",
              value.kind === kind && "border-primary bg-accent/60 ring-1 ring-primary",
            )}
          >
            <span className="block text-sm font-medium">{title}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span>
          </button>
        ))}
      </div>
      {value.kind === "segment" ? (
        <SegmentEditor filters={value.filters} onChange={(filters) => onChange({ ...value, filters })} />
      ) : (
        <SelectedEditor contacts={value.contacts} onChange={(contacts) => onChange({ ...value, contacts })} />
      )}
    </div>
  );
}

function SegmentEditor({ filters, onChange }: { filters: SegmentFilters; onChange: (next: SegmentFilters) => void }) {
  const { data: sources = [] } = useSources();
  const { data: tags = [] } = useTags();
  const { data: users = [] } = useAssignableUsers();
  const set = (patch: Partial<SegmentFilters>) => onChange({ ...filters, ...patch });
  const leads = filters.contact_types.includes("lead");

  return (
    <div className="space-y-4">
      <Checks
        legend="از میان"
        options={[
          { value: "customer" as const, label: "مشتریان" },
          { value: "lead" as const, label: "مشتریان احتمالی" },
        ]}
        value={filters.contact_types}
        onChange={(contact_types) => set({ contact_types })}
        empty="حداقل یکی را انتخاب کنید."
      />
      <Checks
        legend="منبع جذب"
        options={sources.map((s) => ({ value: s.id, label: s.name }))}
        value={filters.source_ids}
        onChange={(source_ids) => set({ source_ids })}
        empty="همه منابع."
      />
      <Checks
        legend="برچسب"
        options={tags.map((t) => ({ value: t.id, label: t.name }))}
        value={filters.tag_ids}
        onChange={(tag_ids) => set({ tag_ids })}
        empty="بدون محدودیت برچسب."
      />
      {leads ? (
        <Checks
          legend="وضعیت مشتری احتمالی"
          options={(Object.entries(LEAD_STATUS_LABELS) as [LeadStatus, string][])
            .filter(([s]) => s !== "converted")
            .map(([value, label]) => ({ value, label }))}
          value={filters.lead_statuses}
          onChange={(lead_statuses) => set({ lead_statuses })}
          empty="همه وضعیت‌ها."
        />
      ) : null}
      <Checks
        legend="مسئول پرونده"
        options={users.map((u) => ({ value: u.id, label: u.full_name }))}
        value={filters.owner_ids}
        onChange={(owner_ids) => set({ owner_ids })}
        empty="همه مسئولان در دامنه شما."
      />
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">تاریخ ثبت</legend>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <DateBound label="از" value={filters.created_from} onChange={(created_from) => set({ created_from })} />
          <DateBound label="تا" value={filters.created_to} onChange={(created_to) => set({ created_to })} />
        </div>
      </fieldset>
    </div>
  );
}

function DateBound({ label, value, onChange }: { label: string; value: string | null; onChange: (v: string | null) => void }) {
  const id = `created-${label}`;
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-muted-foreground">
        {label}
      </label>
      {value ? (
        <>
          <JalaliDateInput id={id} value={value} onChange={onChange} />
          <Button variant="ghost" size="icon-sm" aria-label={`حذف تاریخ ${label}`} onClick={() => onChange(null)}>
            <X />
          </Button>
        </>
      ) : (
        <Button id={id} variant="outline" size="sm" onClick={() => onChange(todayIso())}>
          تعیین تاریخ
        </Button>
      )}
    </div>
  );
}

type Found = { type: "lead" | "customer"; id: string; name: string; mobile: string | null; email: string | null };

function SelectedEditor({ contacts, onChange }: { contacts: ContactRef[]; onChange: (next: ContactRef[]) => void }) {
  const [q, setQ] = useState("");
  const search = useDebounced(q.trim(), 300);
  const { data: found = [], isFetching } = useQuery({
    queryKey: ["campaigns", "contacts", search],
    enabled: search.length >= 2,
    queryFn: async (): Promise<Found[]> => {
      const params = toQuery({ q: search, page_size: 10 });
      const [customers, leads] = await Promise.all([
        apiFetch<Page<Record<string, unknown>>>(`/customers${params}`),
        apiFetch<Page<Record<string, unknown>>>(`/leads${params}`),
      ]);
      const pick = (type: Found["type"]) => (item: Record<string, unknown>): Found => ({
        type,
        id: String(item.id),
        name: String(item.full_name),
        mobile: (item.mobile as string | null) ?? null,
        email: (item.email as string | null) ?? null,
      });
      return [
        ...customers.items.filter((i) => i.access !== "limited").map(pick("customer")),
        ...leads.items.filter((i) => i.access !== "limited" && i.status !== "converted").map(pick("lead")),
      ];
    },
  });
  const chosen = new Set(contacts.map((c) => `${c.type}:${c.id}`));

  return (
    <div className="space-y-3">
      <SearchInput value={q} onChange={setQ} placeholder="جست‌وجوی نام، موبایل یا ایمیل" />
      {search.length >= 2 ? (
        <ul className="divide-y rounded-md border" aria-busy={isFetching}>
          {found.length === 0 ? (
            <li className="p-3 text-center text-sm text-muted-foreground">{isFetching ? "در حال جست‌وجو…" : "پیدا نشد."}</li>
          ) : (
            found.map((f) => {
              const added = chosen.has(`${f.type}:${f.id}`);
              return (
                <li key={`${f.type}:${f.id}`} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="font-medium">{f.name}</span>
                    <span className="ms-2 text-xs text-muted-foreground">
                      {f.type === "lead" ? "مشتری احتمالی" : "مشتری"}
                      {f.mobile ? ` · ${formatMobile(f.mobile)}` : f.email ? ` · ${f.email}` : ""}
                    </span>
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={added}
                    onClick={() => onChange([...contacts, { type: f.type, id: f.id, name: f.name }])}
                  >
                    <Plus aria-hidden />
                    {added ? "افزوده شد" : "افزودن"}
                  </Button>
                </li>
              );
            })
          )}
        </ul>
      ) : null}
      {contacts.length ? (
        <ul className="flex flex-wrap gap-2" aria-label="مخاطبان انتخاب‌شده">
          {contacts.map((c) => (
            <li key={`${c.type}:${c.id}`} className="flex items-center gap-1 rounded-full border bg-card py-0.5 ps-3 pe-1 text-xs">
              {c.name ?? "مخاطب"}
              <span className="text-muted-foreground">({c.type === "lead" ? "احتمالی" : "مشتری"})</span>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`حذف ${c.name ?? "مخاطب"}`}
                onClick={() => onChange(contacts.filter((x) => !(x.type === c.type && x.id === c.id)))}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">هنوز مخاطبی انتخاب نشده است.</p>
      )}
    </div>
  );
}
