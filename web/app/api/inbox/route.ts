import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { backendHeaders, getServerConfig } from "@/lib/server-config";

export async function GET(request: NextRequest) {
  const config = getServerConfig();
  const upstream = new URL(
    `/v1/projects/${config.projectId}/inbox`,
    config.apiUrl,
  );

  request.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.append(key, value);
  });

  return proxyJson(
    fetch(upstream, {
      headers: backendHeaders(config),
      cache: "no-store",
    }),
  );
}
