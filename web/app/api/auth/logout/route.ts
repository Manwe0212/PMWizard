import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  ACCESS_TOKEN_COOKIE,
  PROJECT_COOKIE,
} from "@/lib/session";

export async function POST() {
  const jar = await cookies();
  jar.delete(ACCESS_TOKEN_COOKIE);
  jar.delete(PROJECT_COOKIE);
  return NextResponse.json({ status: "signed_out" });
}
