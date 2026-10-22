import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import {
  ACCESS_TOKEN_COOKIE,
  PROJECT_COOKIE,
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

export async function GET() {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const config = getServerConfig();

  try {
    const [meResponse, projectsResponse] = await Promise.all([
      fetch(`${config.apiUrl}/v1/auth/me`, {
        headers: bearerHeaders(token),
        cache: "no-store",
      }),
      fetch(`${config.apiUrl}/v1/projects`, {
        headers: bearerHeaders(token),
        cache: "no-store",
      }),
    ]);

    if (meResponse.status === 401 || projectsResponse.status === 401) {
      const jar = await cookies();
      jar.delete(ACCESS_TOKEN_COOKIE);
      jar.delete(PROJECT_COOKIE);
      return NextResponse.json(
        { detail: "Session expired. Sign in again." },
        { status: 401 },
      );
    }

    if (!meResponse.ok || !projectsResponse.ok) {
      return NextResponse.json(
        { detail: "Unable to load authenticated PMWizard session." },
        { status: 502 },
      );
    }

    const me = await meResponse.json();
    const projects = await projectsResponse.json();
    const selected = await getSelectedProjectId();
    const selectedValid = projects.items.some(
      (item: { project_id: string }) => item.project_id === selected,
    );

    if (selected && !selectedValid) {
      (await cookies()).delete(PROJECT_COOKIE);
    }

    return NextResponse.json({
      user: me.user,
      projects: projects.items,
      selected_project_id: selectedValid ? selected : null,
    });
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
