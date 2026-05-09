import { NextResponse } from "next/server";

const PROTECTED_PREFIXES = ["/dashboard", "/leaderboard", "/predictions", "/teams", "/matches", "/transfers", "/profile"];
const ADMIN_PREFIX = "/admin";

export function middleware(request) {
  const { pathname } = request.nextUrl;

  const requiresAuth = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const requiresAdmin = pathname.startsWith(ADMIN_PREFIX);

  if (!requiresAuth && !requiresAdmin) {
    return NextResponse.next();
  }

  const accessToken = request.cookies.get("ff_access")?.value;
  const role = request.cookies.get("ff_role")?.value;

  if (!accessToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if (requiresAdmin && role !== "admin") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/leaderboard/:path*", "/predictions/:path*", "/teams/:path*", "/matches/:path*", "/transfers/:path*", "/profile/:path*", "/admin/:path*"],
};
