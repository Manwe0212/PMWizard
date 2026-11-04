import { NextRequest, NextResponse } from "next/server";
import { isSameOrigin } from "./lib/request-origin";

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

  if (!isSameOrigin(request)) {
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
