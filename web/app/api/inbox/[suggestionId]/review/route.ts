import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

type Context = {
  params: Promise<{ suggestionId: string }>;
};

export async function POST(request: Request, context: Context) {
  const { suggestionId } = await context.params;
  const [token, projectId] = await Promise.all([
    getAccessToken(),
    getSelectedProjectId(),
  ]);
  if (!token) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }
  if (!projectId) {
    return NextResponse.json({ detail: "Select a project first." }, { status: 409 });
  }

  const config = getServerConfig();
  const body = await request.text();

  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(
        projectId,
      )}/inbox/${encodeURIComponent(suggestionId)}/review`,
      {
        method: "POST",
        headers: bearerHeaders(token),
        body,
        cache: "no-store",
      },
    ),
  );
}
