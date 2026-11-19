"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { apiFetch, fetchMe, type CurrentUser } from "@/lib/api";
import type {
  Activity,
  Board,
  TimelineEntry,
  TimelineKind,
  Workload,
  Customer,
  Deal,
  DealHistoryEntry,
  Payment,
  Stage,
  Lead,
  LeadSource,
  Organization,
  Page,
  Ref,
  UserRef,
} from "@/lib/types";

export function toQuery(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) {
      search.set(key, String(value));
    }
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export type ListParams = Record<string, string | number | boolean | undefined>;

export const keys = {
  leads: ["leads"] as const,
  customers: ["customers"] as const,
  deals: ["deals"] as const,
  activities: ["activities"] as const,
  timeline: ["timeline"] as const,
  reports: ["reports"] as const,
  settings: ["settings"] as const,
};

export function useLeads(params: ListParams) {
  return useQuery({
    queryKey: [...keys.leads, "list", params],
    queryFn: () => apiFetch<Page<Lead>>(`/leads${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useLead(id: string) {
  return useQuery({ queryKey: [...keys.leads, id], queryFn: () => apiFetch<Lead>(`/leads/${id}`) });
}

export function useCustomers(params: ListParams) {
  return useQuery({
    queryKey: [...keys.customers, "list", params],
    queryFn: () => apiFetch<Page<Customer>>(`/customers${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useCustomer(id: string) {
  return useQuery({
    queryKey: [...keys.customers, id],
    queryFn: () => apiFetch<Customer>(`/customers/${id}`),
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["lead-sources"],
    queryFn: () => apiFetch<LeadSource[]>("/lead-sources"),
    staleTime: 5 * 60_000,
  });
}

export function useTags() {
  return useQuery({ queryKey: ["tags"], queryFn: () => apiFetch<Ref[]>("/tags"), staleTime: 60_000 });
}

export function useAssignableUsers() {
  return useQuery({
    queryKey: ["users", "assignable"],
    queryFn: () => apiFetch<UserRef[]>("/users/assignable"),
    staleTime: 5 * 60_000,
  });
}

export function useOrganizations(q: string) {
  return useQuery({
    queryKey: ["organizations", q],
    queryFn: () => apiFetch<Page<Organization>>(`/organizations${toQuery({ q, page_size: 20 })}`),
    placeholderData: (previous) => previous,
  });
}

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 5 * 60_000 });
}

/** Admins and managers can assign, archive and restore (the API checks the team scope). */
export function canManage(role: CurrentUser["role"] | undefined): boolean {
  return role === "admin" || role === "sales_manager";
}

/** Open tasks waiting in the user's team queues (for the menu badge). */
export function useQueueCount(enabled: boolean) {
  return useQuery({
    queryKey: ["team-tasks", "count"],
    queryFn: async () => (await apiFetch<Page<unknown>>("/team-tasks?page_size=1")).total,
    enabled,
    refetchInterval: 60_000,
  });
}

/** New tickets the user can see (for the menu badge). */
export function useNewTicketCount(enabled: boolean) {
  return useQuery({
    queryKey: ["tickets", "count"],
    queryFn: async () => (await apiFetch<Page<unknown>>("/tickets?status=new&page_size=1")).total,
    enabled,
    refetchInterval: 60_000,
  });
}

export function useStages() {
  return useQuery({ queryKey: ["stages"], queryFn: () => apiFetch<Stage[]>("/stages"), staleTime: 60_000 });
}

export function useBoard(params: ListParams) {
  return useQuery({
    queryKey: [...keys.deals, "board", params],
    queryFn: () => apiFetch<Board>(`/deals/board${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useDeals(params: ListParams) {
  return useQuery({
    queryKey: [...keys.deals, "list", params],
    queryFn: () => apiFetch<Page<Deal>>(`/deals${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useDeal(id: string) {
  return useQuery({ queryKey: [...keys.deals, id], queryFn: () => apiFetch<Deal>(`/deals/${id}`) });
}

export function useDealHistory(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...keys.deals, id, "history"],
    queryFn: () => apiFetch<DealHistoryEntry[]>(`/deals/${id}/history`),
    enabled,
  });
}

export function useDealPayments(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...keys.deals, id, "payments"],
    queryFn: () => apiFetch<Payment[]>(`/deals/${id}/payments`),
    enabled,
  });
}

export function useActivities(params: ListParams) {
  return useQuery({
    queryKey: [...keys.activities, "list", params],
    queryFn: () => apiFetch<Page<Activity>>(`/activities${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useCalendar(params: ListParams) {
  return useQuery({
    queryKey: [...keys.activities, "calendar", params],
    queryFn: () => apiFetch<Activity[]>(`/activities/calendar${toQuery(params)}`),
    placeholderData: (previous) => previous,
  });
}

export function useWorkload(ownerId?: string) {
  return useQuery({
    queryKey: [...keys.activities, "workload", ownerId ?? "me"],
    queryFn: () => apiFetch<Workload>(`/activities/workload${toQuery({ owner_id: ownerId })}`),
    refetchInterval: 5 * 60_000,
  });
}

export function useOwnerDay(ownerId: string | undefined, day: string | null) {
  return useQuery({
    queryKey: [...keys.activities, "day", ownerId, day],
    queryFn: () => apiFetch<Activity[]>(`/activities/day${toQuery({ owner_id: ownerId, day })}`),
    enabled: Boolean(ownerId && day),
  });
}

export type TimelineSubject = { deal_id?: string; customer_id?: string; lead_id?: string };

export function useTimeline(subject: TimelineSubject, kinds: TimelineKind[] | null) {
  return useInfiniteQuery({
    queryKey: [...keys.timeline, subject, kinds],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const search = new URLSearchParams(toQuery({ ...subject, limit: 20, before: pageParam ?? undefined }).slice(1));
      for (const k of kinds ?? []) search.append("kinds", k);
      return apiFetch<{ items: TimelineEntry[]; has_more: boolean }>(`/timeline?${search.toString()}`);
    },
    getNextPageParam: (last) => (last.has_more ? (last.items.at(-1)?.at ?? null) : null),
  });
}

export type ReportSummary = {
  currency: string;
  date_from: string;
  date_to: string;
  evaluated_on: string;
  sales: { count: number; amount: number };
  received: number;
  unpaid_balance: number;
  pipeline: { count: number; amount: number };
  new_leads: number;
  new_customers: number;
  first_purchase_customers: number;
  win_rate: { numerator: number; denominator: number; rate: number | null };
  lead_conversion: { numerator: number; denominator: number; rate: number | null };
  first_contact_median_hours: number | null;
  overdue_activities: number;
  deals_without_next_action: number;
};

export type InboundRow = { key: string; label: string; open: number; won: number; lost: number };

/** Any report endpoint; the payload type is chosen by the caller. */
export function useReport<T>(path: string, params: ListParams, enabled = true) {
  return useQuery({
    queryKey: [...keys.reports, path, params],
    queryFn: () => apiFetch<T>(`/reports/${path}${toQuery(params)}`),
    placeholderData: (previous) => previous,
    enabled,
  });
}

/** Settings data: users, teams, stages (incl. inactive), sources, audit. */
export function useSettings<T>(path: string, params: ListParams = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.settings, path, params],
    queryFn: () => apiFetch<T>(`${path}${toQuery(params)}`),
    enabled,
  });
}
