import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/request-origin";
import { getServerConfig } from "@/lib/server-config";
import {
  ACCESS_TOKEN_COOKIE,
  PROJECT_COOKIE,
  bearerHeaders,
  getAccessToken,
} from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }
  try {
    const response = await fetch(`${getServerConfig().apiUrl}/v1/auth/logout-all`, {
      method: "POST",
      headers: bearerHeaders(token),
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json(
        { detail: "Unable to revoke all sessions. Try again." },
        { status: response.status === 401 ? 401 : 502 },
      );
    }
    const jar = await cookies();
    jar.delete(ACCESS_TOKEN_COOKIE);
    jar.delete(PROJECT_COOKIE);
    return NextResponse.json(
      { status: "all_sessions_revoked" },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}
