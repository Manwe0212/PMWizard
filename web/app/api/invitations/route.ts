import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/request-origin";
import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken, getSelectedProjectId } from "@/lib/session";

async function scope() {
  const [token, projectId] = await Promise.all([getAccessToken(), getSelectedProjectId()]);
  if (!token) {
    return { error: NextResponse.json({ detail: "Authentication required." }, { status: 401 }) };
  }
  if (!projectId) {
    return { error: NextResponse.json({ detail: "Select a project first." }, { status: 409 }) };
  }
  return { token, projectId };
}

export async function GET(request: NextRequest) {
  const context = await scope();
  if (context.error) return context.error;
  const params = new URLSearchParams();
  for (const key of ["limit", "offset"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) params.set(key, value);
  }
  const suffix = params.toString();
  try {
    const upstream = await fetch(
      `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(context.projectId!)}/invitations${suffix ? `?${suffix}` : ""}`,
      { headers: bearerHeaders(context.token!), cache: "no-store" },
    );
    const data = await upstream.json().catch(() => ({}));
    return NextResponse.json(
      upstream.ok ? data : { detail: typeof data.detail === "string" ? data.detail : "Unable to load invitations." },
      { status: upstream.status, headers: { "Cache-Control": "private, no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}

export async function POST(request: NextRequest) {
  const context = await scope();
  if (context.error) return context.error;
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 1000) {
    return NextResponse.json({ detail: "Invitation request too large." }, { status: 413 });
  }
  let body: unknown;
  try { body = JSON.parse(raw); } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  try {
    const upstream = await fetch(
      `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(context.projectId!)}/invitations`,
      {
        method: "POST",
        headers: bearerHeaders(context.token!),
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );
    const data = await upstream.json().catch(() => ({}));
    return NextResponse.json(
      upstream.ok ? data : { detail: typeof data.detail === "string" ? data.detail : "Unable to create invitation." },
      { status: upstream.status, headers: { "Cache-Control": "private, no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}
