import { NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken, getSelectedProjectId } from "@/lib/session";

type Context = { params: Promise<{ invitationId: string }> };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function DELETE(request: NextRequest, context: Context) {
  const [{ invitationId }, token, projectId] = await Promise.all([
    context.params, getAccessToken(), getSelectedProjectId(),
  ]);
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }
  if (!projectId) {
    return NextResponse.json({ detail: "Select a project first." }, { status: 409 });
  }
  if (!UUID.test(invitationId)) {
    return NextResponse.json({ detail: "Invalid invitation ID." }, { status: 422 });
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  try {
    const response = await fetch(
      `${getServerConfig().apiUrl}/v1/projects/${encodeURIComponent(projectId)}/invitations/${encodeURIComponent(invitationId)}`,
      { method: "DELETE", headers: bearerHeaders(token), cache: "no-store" },
    );
    if (response.status === 204) {
      return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
    }
    const data = await response.json().catch(() => ({}));
    return NextResponse.json(
      { detail: typeof data.detail === "string" ? data.detail : "Unable to revoke invitation." },
      { status: response.status, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json({ detail: "PMWizard API is unavailable." }, { status: 502 });
  }
}
