import { NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import {
  bearerHeaders,
  getAccessToken,
  getSelectedProjectId,
} from "@/lib/session";

const ALLOWED_PARAMS = new Set(["format", "category", "actor_id", "since", "until"]);

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

  const params = new URLSearchParams();
  request.nextUrl.searchParams.forEach((value, key) => {
    if (ALLOWED_PARAMS.has(key)) params.append(key, value);
  });

  try {
    const config = getServerConfig();
    const suffix = params.toString();
    const upstream = await fetch(
      `${config.apiUrl}/v1/projects/${encodeURIComponent(projectId)}/activity/export${suffix ? `?${suffix}` : ""}`,
      {
        headers: bearerHeaders(token),
        cache: "no-store",
      },
    );

    if (!upstream.ok) {
      const payload = await upstream.json().catch(() => ({}));
      return NextResponse.json(
        {
          detail: typeof payload?.detail === "string"
            ? payload.detail
            : "Unable to export project activity.",
        },
        { status: upstream.status },
      );
    }

    const headers = new Headers({
      "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of [
      "Content-Disposition",
      "X-PMWizard-Export-SHA256",
      "X-PMWizard-Export-Count",
      "X-PMWizard-Export-Truncated",
    ]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }

    return new NextResponse(await upstream.text(), {
      status: 200,
      headers,
    });
  } catch {
    // Do not disclose internal backend URLs or provider errors to clients.
    return NextResponse.json(
      { detail: "PMWizard export service is temporarily unavailable." },
      { status: 502 },
    );
  }
}
