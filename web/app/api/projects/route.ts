import { NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken } from "@/lib/session";

const MAX_BODY_BYTES = 5000;

export async function POST(request: Request) {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return NextResponse.json({ detail: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON request required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return NextResponse.json({ detail: "Project request is too large." }, { status: 413 });
  }
  let input: unknown;
  try {
    input = JSON.parse(raw);
  } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return NextResponse.json({ detail: "Project payload must be an object." }, { status: 422 });
  }

  try {
    const apiUrl = getServerConfig().apiUrl;
    const response = await fetch(`${apiUrl}/v1/projects`, {
      method: "POST",
      headers: bearerHeaders(token),
      body: JSON.stringify(input),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof payload?.detail === "string"
        ? payload.detail
        : "Project creation failed. Please review the entered values.";
      return NextResponse.json({ detail }, { status: response.status });
    }
    return NextResponse.json(payload, {
      status: 201,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "PMWizard API is unavailable from the web server." },
      { status: 502 },
    );
  }
}
