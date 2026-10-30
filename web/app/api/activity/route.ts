import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

const ALLOWED_PARAMS = new Set(["category", "actor_id", "since", "until", "cursor", "limit"]);

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

  // Forward only documented filters. The selected project comes from the
  // authenticated server-side session, never from a browser-supplied ID.
  const params = new URLSearchParams();
  request.nextUrl.searchParams.forEach((value, key) => {
    if (ALLOWED_PARAMS.has(key)) {
      params.append(key, value);
    }
  });

  const config = getServerConfig();
  const suffix = params.toString();
  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(projectId)}/activity${suffix ? `?${suffix}` : ""}`,
      { headers: bearerHeaders(token), cache: "no-store" },
    ),
  );
}
