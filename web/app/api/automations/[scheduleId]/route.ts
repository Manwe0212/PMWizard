import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

type Context = {
  params: Promise<{ scheduleId: string }>;
};

export async function PATCH(request: NextRequest, context: Context) {
  const [{ scheduleId }, token, projectId] = await Promise.all([
    context.params,
    getAccessToken(),
    getSelectedProjectId(),
  ]);

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
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        projectId,
      )}/automations/${encodeURIComponent(scheduleId)}`,
      {
        method: "PATCH",
        headers: bearerHeaders(token),
        body: JSON.stringify(body),
        cache: "no-store",
      },
    ),
  );
}
