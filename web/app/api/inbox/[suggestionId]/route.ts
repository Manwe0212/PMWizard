import { proxyJson } from "@/lib/proxy";
import { backendHeaders, getServerConfig } from "@/lib/server-config";

type Context = {
  params: Promise<{ suggestionId: string }>;
};

export async function GET(_request: Request, context: Context) {
  const { suggestionId } = await context.params;
  const config = getServerConfig();

  return proxyJson(
    fetch(
      `${config.apiUrl}/v1/projects/${config.projectId}/inbox/${encodeURIComponent(
        suggestionId,
      )}`,
      {
        headers: backendHeaders(config),
        cache: "no-store",
      },
    ),
  );
}
