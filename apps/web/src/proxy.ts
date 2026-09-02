import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// UX-only redirect: this cannot decode or verify the httpOnly JWT cookie (it's
// signed by the backend and middleware has no reason to hold that secret), so
// it only checks the cookie's presence. The real enforcement boundary is the
// API's get_current_user dependency (see apps/api/app/auth/dependencies.py).
const SESSION_COOKIE_NAME = "session";
const PUBLIC_PATHS = ["/login", "/register"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublicPath = PUBLIC_PATHS.some((path) => pathname.startsWith(path));
  const hasSessionCookie = request.cookies.has(SESSION_COOKIE_NAME);

  if (!isPublicPath && !hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
