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
  let revoked = !token;
  if (token) {
    try {
      const response = await fetch(`${getServerConfig().apiUrl}/v1/auth/logout`, {
        method: "POST",
        headers: bearerHeaders(token),
        cache: "no-store",
      });
      revoked = response.status === 204 || response.status === 401;
    } catch {
      revoked = false;
    }
  }

  const jar = await cookies();
  jar.delete(ACCESS_TOKEN_COOKIE);
  jar.delete(PROJECT_COOKIE);
  if (!revoked) {
    return NextResponse.json(
      { detail: "Signed out of this browser, but server-side revocation could not be confirmed." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.json(
    { status: "signed_out" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
