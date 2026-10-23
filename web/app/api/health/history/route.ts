import { NextResponse } from "next/server";

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

  return { token, projectId, config: getServerConfig() };
}

export async function GET() {
  const resolved = await context();
  if ("error" in resolved) return resolved.error;

  const { token, projectId, config } = resolved;
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        projectId,
      )}/health/history?limit=90`,
      {
        headers: bearerHeaders(token),
        cache: "no-store",
      },
    ),
  );
}

export async function POST() {
  const resolved = await context();
  if ("error" in resolved) return resolved.error;

  const { token, projectId, config } = resolved;
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        projectId,
      )}/health/snapshots`,
      {
        method: "POST",
        headers: bearerHeaders(token),
        cache: "no-store",
      },
    ),
  );
}
