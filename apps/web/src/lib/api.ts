/** Browser client for the CRM API (served under /api on the web origin). */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly retryAfter?: number,
  ) {
    super(message);
  }
}

const CSRF_COOKIE = "crm_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const GENERIC_ERROR = "خطایی رخ داد. دوباره تلاش کنید.";

function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

// Concurrent 401s share one refresh, so the refresh token rotates once.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshInFlight ??= fetch("/api/auth/refresh", {
    method: "POST",
    headers: { [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? "" },
  })
    .then((res) => res.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export function redirectToLogin() {
  const next = window.location.pathname + window.location.search;
  // Full reload on purpose: the session ended, so discard all client state.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (method !== "GET" && method !== "HEAD") headers.set(CSRF_HEADER, readCookie(CSRF_COOKIE) ?? "");

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, method, headers });
  } catch {
    throw new ApiError(0, "ارتباط با سرور برقرار نشد.");
  }

  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return apiFetch<T>(path, init, false);
    redirectToLogin();
  }
  if (!res.ok) {
    let message = GENERIC_ERROR;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // keep the generic message
    }
    const retryAfter = Number(res.headers.get("Retry-After")) || undefined;
    throw new ApiError(res.status, message, retryAfter);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export type CurrentUser = {
  id: string;
  full_name: string;
  role: "admin" | "sales_manager" | "sales_rep";
  team_id: string | null;
  mobile: string | null;
  email: string | null;
};

/** Current user, refreshing the access token once if it has expired. */
export async function fetchMe(): Promise<CurrentUser> {
  try {
    return await apiFetch<CurrentUser>("/auth/me", {}, false);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && (await refreshSession())) {
      return apiFetch<CurrentUser>("/auth/me", {}, false);
    }
    throw err;
  }
}
