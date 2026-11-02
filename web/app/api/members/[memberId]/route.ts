import { NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken, getSelectedProjectId } from "@/lib/session";

type Context = { params: Promise<{ memberId: string }> };
const UUID_FORMAT = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

async function requestScope(request: NextRequest, context: Context) {
  const [{ memberId }, token, projectId] = await Promise.all([
    context.params,
    getAccessToken(),
    getSelectedProjectId(),
  ]);
  if (!token) {
    return { error: NextResponse.json({ detail: "Authentication required." }, { status: 401 }) };
  }
  if (!projectId) {
    return { error: NextResponse.json({ detail: "Select a project first." }, { status: 409 }) };
  }
  if (!UUID_FORMAT.test(memberId)) {
    return { error: NextResponse.json({ detail: "Invalid member ID." }, { status: 422 }) };
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return { error: NextResponse.json({ detail: "Cross-origin requests are not allowed." }, { status: 403 }) };
  }
  return { token, url: `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(memberId)}` };
}

async function requestBackend(url: string, token: string, method: "PATCH" | "DELETE", body?: string) {
  try {
    const response = await fetch(url, {
      method,
      headers: bearerHeaders(token),
      ...(body ? { body } : {}),
      cache: "no-store",
    });
    if (response.status === 204) {
      return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
    }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { detail: typeof payload?.detail === "string" ? payload.detail : "Membership change failed." },
        { status: response.status },
      );
    }
    return NextResponse.json(payload, {
      status: response.status,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "PMWizard membership API is unavailable." }, { status: 502 });
  }
}

export async function PATCH(request: NextRequest, context: Context) {
  const auth = await requestScope(request, context);
  if (auth.error) return auth.error;
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON request required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 500) {
    return NextResponse.json({ detail: "Role request is too large." }, { status: 413 });
  }
  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return NextResponse.json({ detail: "Invalid JSON." }, { status: 422 });
  }
  return requestBackend(auth.url!, auth.token!, "PATCH", JSON.stringify(payload));
}

export async function DELETE(request: NextRequest, context: Context) {
  const auth = await requestScope(request, context);
  if (auth.error) return auth.error;
  return requestBackend(auth.url!, auth.token!, "DELETE");
}
