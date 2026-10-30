import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

async function context() {
  return Promise.all([getAccessToken(), getSelectedProjectId()]);
}

export async function GET() {
  const [token, projectId] = await context();
  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required." },
      { status: 401 },
    );
  }
  if (!projectId) {
    return NextResponse.json(
      { detail: "Select a project first." },
      { status: 409 },
    );
  }

  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(projectId)}/notifications`,
      {
        headers: bearerHeaders(token),
        cache: "no-store",
      },
    ),
  );
}

export async function PUT(request: NextRequest) {
  const [token, projectId] = await context();
  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required." },
      { status: 401 },
    );
  }
  if (!projectId) {
    return NextResponse.json(
      { detail: "Select a project first." },
      { status: 409 },
    );
  }

  const body = await request.json().catch(() => ({}));
  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(projectId)}/notifications`,
      {
        method: "PUT",
        headers: bearerHeaders(token),
        body: JSON.stringify(body),
        cache: "no-store",
      },
    ),
  );
}
