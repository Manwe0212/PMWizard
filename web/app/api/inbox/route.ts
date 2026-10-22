import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

export async function GET(request: NextRequest) {
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
  const upstream = new URL(
    `/v1/projects/${encodeURIComponent(projectId)}/inbox`,
    config.apiUrl,
  );
  request.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.append(key, value);
  });

  return proxyJson(
    fetch(upstream, {
      headers: bearerHeaders(token),
      cache: "no-store",
    }),
  );
}
