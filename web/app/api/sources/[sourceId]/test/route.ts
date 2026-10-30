import { NextResponse } from "next/server";

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

export async function POST(_request: Request, context: Context) {
  const [{ sourceId }, token, projectId] = await Promise.all([
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

  const config = getServerConfig();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        projectId,
      )}/sources/${encodeURIComponent(sourceId)}/test`,
      {
        method: "POST",
        headers: bearerHeaders(token),
        cache: "no-store",
      },
    ),
  );
}
