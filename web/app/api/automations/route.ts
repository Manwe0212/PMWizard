import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

async function context() {
  const [token, projectId] = await Promise.all([
    getAccessToken(),
    getSelectedProjectId(),
  ]);
  if (!token) {
    return {
      error: NextResponse.json(
        { detail: "Authentication required." },
        { status: 401 },
      ),
    };
  }
  if (!projectId) {
    return {
      error: NextResponse.json(
        { detail: "Select a project first." },
        { status: 409 },
      ),
    };
  }
  return { token, projectId };
}

export async function GET() {
  const current = await context();
  if ("error" in current) return current.error;

  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        current.projectId,
      )}/automations`,
      {
        headers: bearerHeaders(current.token),
        cache: "no-store",
      },
    ),
  );
}

export async function POST(request: NextRequest) {
  const current = await context();
  if ("error" in current) return current.error;

  const body = await request.json().catch(() => ({}));
  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        current.projectId,
      )}/automations`,
      {
        method: "POST",
        headers: bearerHeaders(current.token),
        body: JSON.stringify(body),
        cache: "no-store",
      },
    ),
  );
}
