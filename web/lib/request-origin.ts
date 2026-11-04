/**
 * Validate the browser Origin against the actual public application origin.
 *
 * In production the canonical HTTPS origin is the explicitly configured
 * deployment origin; never infer it from untrusted forwarded host headers.
 *
 * In localhost development Next.js may normalize request.nextUrl.origin to
 * "localhost" while the browser legitimately uses "127.0.0.1". The actual
 * HTTP Host sent by the browser is authoritative for SAME-HOST development
 * checks, rather than NextURL's internally normalized origin.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const production = process.env.NODE_ENV === "production";
  if (!origin) {
    return !production;
  }

  if (production) {
    const expected = process.env.PMWIZARD_PUBLIC_BASE_URL?.trim().replace(/\/+$/, "");
    return !!expected && expected.startsWith("https://") && origin === expected;
  }

  const host = request.headers.get("host");
  if (!host || /[\s/?#@\\]/.test(host)) {
    return false;
  }
  const protocol = new URL(request.url).protocol;
  return origin === `${protocol}//${host}`;
}
