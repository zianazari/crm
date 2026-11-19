import { NextResponse, type NextRequest } from "next/server";

// Optimistic check only: real authentication happens in the API on every request.
// With neither cookie there is no way to be signed in, so go straight to /login.
export function proxy(request: NextRequest) {
  const hasSession =
    request.cookies.has("crm_access") || request.cookies.has("crm_refresh");
  if (hasSession) return NextResponse.next();

  const login = new URL("/login", request.url);
  const target = request.nextUrl.pathname + request.nextUrl.search;
  if (target !== "/") login.searchParams.set("next", target);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the login page, the customer portal (its own login and guard), the
  // public unsubscribe page (/u/<token>), the booking page (/book/<token>), the API rewrite and static assets.
  matcher: ["/((?!login|portal|book/|u/|api|_next/static|_next/image|favicon.ico|.*\\.(?:png|svg|ico|woff2?)$).*)"],
};
