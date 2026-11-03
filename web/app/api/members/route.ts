import { NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken, getSelectedProjectId } from "@/lib/session";

async function scope() {
  const [token, projectId] = await Promise.all([
    getAccessToken(), getSelectedProjectId(),
  ]);
  if (!token) {
    return { error: NextResponse.json({ detail: "Authentication required." }, { status: 401 }) };
  }
  if (!projectId) {
    return { error: NextResponse.json({ detail: "Select a project first." }, { status: 409 }) };
  }
  return { token, projectId };
}

async function forward(url: string, token: string, init?: RequestInit) {
  try {
    const response = await fetch(url, {
      ...init,
      headers: bearerHeaders(token),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { detail: typeof payload?.detail === "string" ? payload.detail : "Membership request failed." },
        { status: response.status },
      );
    }
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "PMWizard membership API is unavailable." },
      { status: 502 },
    );
  }
}

export async function GET(request: NextRequest) {
  const auth = await scope();
  if (auth.error) return auth.error;
  const params = new URLSearchParams();
  for (const key of ["limit", "offset"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) params.set(key, value);
  }
  const suffix = params.toString();
  const url = `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(auth.projectId!)}/members${suffix ? `?${suffix}` : ""}`;
  return forward(url, auth.token!);
}

export async function POST(request: NextRequest) {
  const auth = await scope();
  if (auth.error) return auth.error;
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Cross-origin requests are not allowed." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON request required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 1000) {
    return NextResponse.json({ detail: "Member request is too large." }, { status: 413 });
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  const url = `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(auth.projectId!)}/members`;
  return forward(url, auth.token!, { method: "POST", body: JSON.stringify(payload) });
}
