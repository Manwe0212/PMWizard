import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/request-origin";
import { getServerConfig } from "@/lib/server-config";
import { ACCESS_TOKEN_COOKIE, PROJECT_COOKIE, cookieOptions } from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 2500) {
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  }
  let body: unknown;
  try { body = JSON.parse(raw); } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }

  try {
    const upstream = await fetch(`${getServerConfig().apiUrl}/v1/invitations/accept`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const result = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      return NextResponse.json(
        { detail: typeof result.detail === "string" ? result.detail : "Invitation cannot be accepted." },
        { status: upstream.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    const jar = await cookies();
    jar.set(ACCESS_TOKEN_COOKIE, result.access_token, cookieOptions(result.expires_in));
    jar.set(PROJECT_COOKIE, result.project_id, cookieOptions(result.expires_in));
    return NextResponse.json(
      { user: result.user, project_id: result.project_id },
      { headers: { "Cache-Control": "private, no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}
