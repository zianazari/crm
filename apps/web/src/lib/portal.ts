/** Client for the customer portal API (/api/portal/*). Separate from the staff client:
 * its own CSRF cookie, and a lost session goes back to the portal login. */

import { ApiError } from "@/lib/api";
import type { Page } from "@/lib/types";

const CSRF_COOKIE = "crm_portal_csrf";

function csrf(): string {
  return (
    document.cookie
      .split("; ")
      .find((part) => part.startsWith(`${CSRF_COOKIE}=`))
      ?.slice(CSRF_COOKIE.length + 1) ?? ""
  );
}

export function toPortalLogin() {
  const next = window.location.pathname;
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/portal/login?next=${encodeURIComponent(next)}`);
}

export async function portalFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (method !== "GET") headers.set("X-CSRF-Token", csrf());
  let res: Response;
  try {
    res = await fetch(`/api/portal${path}`, { ...init, method, headers });
  } catch {
    throw new ApiError(0, "ارتباط با سرور برقرار نشد.");
  }
  if (res.status === 401) {
    toPortalLogin();
    throw new ApiError(401, "لطفاً دوباره وارد شوید.");
  }
  if (!res.ok) {
    let message = "خطایی رخ داد. دوباره تلاش کنید.";
    try {
      const detail = ((await res.json()) as { detail?: unknown }).detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) message = "اطلاعات واردشده کامل نیست.";
    } catch {
      // keep the generic message
    }
    throw new ApiError(res.status, message, Number(res.headers.get("Retry-After")) || undefined);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export type PortalMe = { customer_name: string; channel: "sms" | "email"; address: string };

export type TicketStatus = "new" | "in_progress" | "waiting_customer" | "closed";

export type PortalTicket = {
  id: string;
  number: number;
  subject: string;
  status: TicketStatus;
  status_label: string;
  created_at: string;
  last_message_at: string;
};

export type PortalMessage = { id: string; body: string; from_me: boolean; author: string; created_at: string };
export type PortalTicketDetail = PortalTicket & { messages: PortalMessage[] };
export type PortalTicketPage = Page<PortalTicket>;
