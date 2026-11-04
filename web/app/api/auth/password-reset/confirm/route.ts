import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/request-origin";
import { getServerConfig } from "@/lib/server-config";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 1500) {
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  }
  let body: unknown;
  try { body = JSON.parse(raw); } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  try {
    const response = await fetch(`${getServerConfig().apiUrl}/v1/auth/password-reset/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json(
        { detail: response.status === 400
          ? "Reset link is invalid, expired or already used."
          : response.status === 503
            ? "Password recovery is not configured."
            : "Password change failed." },
        { status: response.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      { status: "password_updated", sessions: "revoked" },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}
