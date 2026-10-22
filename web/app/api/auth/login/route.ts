import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { getServerConfig } from "@/lib/server-config";
import {
  ACCESS_TOKEN_COOKIE,
  PROJECT_COOKIE,
  cookieOptions,
} from "@/lib/session";

export async function POST(request: Request) {
  const config = getServerConfig();
  const body = await request.text();

  try {
    const response = await fetch(`${config.apiUrl}/v1/auth/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    });

    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;

    if (!response.ok) {
      return NextResponse.json(payload, { status: response.status });
    }

    const jar = await cookies();
    jar.set(
      ACCESS_TOKEN_COOKIE,
      payload.access_token,
      cookieOptions(payload.expires_in),
    );
    jar.delete(PROJECT_COOKIE);

    return NextResponse.json({
      user: payload.user,
      expires_in: payload.expires_in,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "PMWizard API is unavailable from the web server.",
        diagnostic:
          error instanceof Error ? error.message : "Unknown backend error",
      },
      { status: 502 },
    );
  }
}
