import { NextResponse } from "next/server";

import { proxyJson } from "@/lib/proxy";
import { getServerConfig } from "@/lib/server-config";
import { bearerHeaders, getAccessToken } from "@/lib/session";

export async function GET() {
  const token = await getAccessToken();
  if (!token) {
    return NextResponse.json(
      { detail: "Authentication required." },
      { status: 401 },
    );
  }

  const config = getServerConfig();
  return proxyJson(
    fetch(`${config.apiUrl}/v1/executive/dashboard`, {
      headers: bearerHeaders(token),
      cache: "no-store",
    }),
  );
}
