import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import {
  PROJECT_COOKIE,
  bearerHeaders,
  cookieOptions,
  getAccessToken,
} from "@/lib/session";

export async function POST(request: Request) {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const payload = await request.json().catch(() => null);
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
  } catch (error) {
    return NextResponse.json(
      {
        detail: "PMWizard API is unavailable from the web server.",
        diagnostic:
          error instanceof Error ? error.message : "Unknown backend error",
      },
      { status: 502 },
    );
  }
}
