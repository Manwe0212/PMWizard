import { NextRequest, NextResponse } from "next/server";

/**
 * Additional CSRF gate for the cookie-authenticated BFF.
 *
 * Browser mutations carry an Origin; in production, absent Origin is
 * rejected as well. The reverse proxy must preserve the public Host and
 * HTTPS scheme. Direct API access still requires bearer authentication.
 */
export function proxy(request: NextRequest) {
  const method = request.method.toUpperCase();
  if (["GET", "HEAD", "OPTIONS"].includes(method)) {
    return NextResponse.next();
  }

  const origin = request.headers.get("origin");
  const production = process.env.NODE_ENV === "production";
  const expected = production
    ? process.env.PMWIZARD_PUBLIC_BASE_URL?.trim().replace(/\/+$/, "")
    : request.nextUrl.origin;

  if (
    (production && (!origin || !expected || !expected.startsWith("https://"))) ||
    (origin && origin !== expected)
  ) {
    return NextResponse.json(
      { detail: "Cross-origin or unverifiable request denied." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/:path*"],
};
