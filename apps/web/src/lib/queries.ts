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
