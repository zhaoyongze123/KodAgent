import { proxyAgentRequest } from "../../_lib";

export const runtime = "nodejs";

type Context = { params: Promise<{ providerId: string }> };

export async function DELETE(request: Request, { params }: Context) {
  const { providerId } = await params;
  return proxyAgentRequest(
    request,
    `/admin-api/agent/model-providers/${encodeURIComponent(providerId)}`,
    "model:manage",
    { method: "DELETE" },
  );
}
