import { NextResponse, type NextRequest } from "next/server";

/**
 * 1. Forwards /api/* to the backend so the browser talks to a single origin
 *    (cookies stay first-party; no CORS). The target is read at request time from
 *    API_INTERNAL_URL, so one image works in every environment.
 * 2. Optimistic redirect to /sign-in when no session cookie is present. This is a UX
 *    shortcut only: the API validates the session on every request.
 */

const PUBLIC_PATHS = ["/sign-in", "/forgot-password", "/reset-password", "/accept-invitation"];

function apiOrigin(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api/")) {
    return NextResponse.rewrite(new URL(`${pathname}${search}`, apiOrigin()));
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (!isPublic && !request.cookies.has("wp_session")) {
    const signIn = new URL("/sign-in", request.url);
    if (pathname !== "/") signIn.searchParams.set("next", pathname);
    return NextResponse.redirect(signIn);
  }
  return NextResponse.next();
}

export const config = {
  // Skip Next.js internals and static files.
  matcher: ["/((?!_next/static|_next/image|icon.svg|favicon.ico|robots.txt).*)"],
};
