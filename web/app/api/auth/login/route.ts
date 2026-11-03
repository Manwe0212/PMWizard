import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import {
  ACCESS_TOKEN_COOKIE,
  PROJECT_COOKIE,
  cookieOptions,
} from "@/lib/session";

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 1600) {
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  }
  let body: unknown;
  try { body = JSON.parse(raw); } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  try {
    const response = await fetch(`${getServerConfig().apiUrl}/v1/auth/login`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json(
        { detail: response.status === 401
          ? "Invalid email or password."
          : response.status === 429
            ? "Too many login attempts. Try later."
            : "Unable to sign in." },
        { status: response.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    const payload = await response.json();
    const jar = await cookies();
    jar.set(
      ACCESS_TOKEN_COOKIE,
      payload.access_token,
      cookieOptions(payload.expires_in),
    );
    jar.delete(PROJECT_COOKIE);
    return NextResponse.json(
      { user: payload.user, expires_in: payload.expires_in },
      { headers: { "Cache-Control": "private, no-store" } },
    );
  } catch {
    // Never return upstream network diagnostics, credentials or request body.
    return NextResponse.json(
      { detail: "PMWizard API is unavailable from the web server." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
