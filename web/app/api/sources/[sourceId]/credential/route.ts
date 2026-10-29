import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

type Context = {
  params: Promise<{ sourceId: string }>;
};

async function context(current: Context) {
  const [{ sourceId }, token, projectId] = await Promise.all([
    current.params,
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
  return { sourceId, token, projectId };
}

export async function PUT(request: NextRequest, routeContext: Context) {
  const current = await context(routeContext);
  if ("error" in current) return current.error;

  const body = await request.json().catch(() => ({}));
  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        current.projectId,
      )}/sources/${encodeURIComponent(current.sourceId)}/credential`,
      {
        method: "PUT",
        headers: bearerHeaders(current.token),
        body: JSON.stringify(body),
        cache: "no-store",
      },
    ),
  );
}

export async function DELETE(_request: Request, routeContext: Context) {
  const current = await context(routeContext);
  if ("error" in current) return current.error;

  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        current.projectId,
      )}/sources/${encodeURIComponent(current.sourceId)}/credential`,
      {
        method: "DELETE",
        headers: bearerHeaders(current.token),
        cache: "no-store",
      },
    ),
  );
}
