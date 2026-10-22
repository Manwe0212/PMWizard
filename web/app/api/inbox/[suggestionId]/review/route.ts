import { proxyJson } from "@/lib/proxy";
import { backendHeaders, getServerConfig } from "@/lib/server-config";

type Context = {
  params: Promise<{ suggestionId: string }>;
};

export async function POST(request: Request, context: Context) {
  const { suggestionId } = await context.params;
  const config = getServerConfig();
  const body = await request.text();

  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${config.projectId}/inbox/${encodeURIComponent(
        suggestionId,
      )}/review`,
      {
        method: "POST",
        headers: backendHeaders(config),
        body,
        cache: "no-store",
      },
    ),
  );
}
