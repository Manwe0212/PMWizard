import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/request-origin";
import { getServerConfig } from "@/lib/server-config";
import {
  PROJECT_COOKIE,
  bearerHeaders,
  cookieOptions,
  getAccessToken,
} from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request denied." }, { status: 403 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return NextResponse.json({ detail: "JSON request required." }, { status: 415 });
  }
  const raw = await request.text();
  if (raw.length > 1000) {
    return NextResponse.json({ detail: "Project selection request too large." }, { status: 413 });
  }
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const payload = (() => { try { return JSON.parse(raw); } catch { return null; } })();
  const projectId =
    payload && typeof payload.project_id === "string"
      ? payload.project_id.trim()
      : "";
  if (!projectId) {
    return NextResponse.json({ detail: "project_id is required." }, { status: 422 });
  }

  const config = getServerConfig();

  try {
    const response = await fetch(`${config.apiUrl}/v1/projects`, {
      headers: bearerHeaders(token),
      cache: "no-store",
    });
    if (!response.ok) {
      return NextResponse.json(
        { detail: "Unable to validate project access." },
        { status: response.status },
      );
    }

    const projects = await response.json();
    const allowed = projects.items.some(
      (item: { project_id: string }) => item.project_id === projectId,
    );
    if (!allowed) {
      return NextResponse.json(
        { detail: "Project not found or not authorized." },
        { status: 404 },
      );
    }

    (await cookies()).set(PROJECT_COOKIE, projectId, cookieOptions());
    return NextResponse.json({ project_id: projectId });
  } catch {
    return NextResponse.json(
      { detail: "PMWizard project selection is temporarily unavailable." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
