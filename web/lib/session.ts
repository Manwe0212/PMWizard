import { cookies } from "next/headers";

export const ACCESS_TOKEN_COOKIE = "pmwizard_access_token";
export const PROJECT_COOKIE = "pmwizard_project_id";

export async function getAccessToken(): Promise<string | null> {
  return (await cookies()).get(ACCESS_TOKEN_COOKIE)?.value ?? null;
}

export async function getSelectedProjectId(): Promise<string | null> {
  return (await cookies()).get(PROJECT_COOKIE)?.value ?? null;
}

export function bearerHeaders(token: string): HeadersInit {
  return {
    Accept: "application/json",
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

export function cookieOptions(maxAge?: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    ...(maxAge !== undefined ? { maxAge } : {}),
  };
}
