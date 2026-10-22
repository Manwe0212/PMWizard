import { NextResponse } from "next/server";

export async function proxyJson(request: Promise<Response>): Promise<NextResponse> {
  try {
    const response = await request;
    const text = await response.text();
    const body = text ? JSON.parse(text) : null;
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown backend error";
    return NextResponse.json(
      {
        detail:
          "PMWizard API is unavailable from the web server.",
        diagnostic: message,
      },
      { status: 502 },
    );
  }
}
