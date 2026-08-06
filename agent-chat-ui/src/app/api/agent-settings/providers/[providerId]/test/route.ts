import { proxyAgentRequest } from "../../../_lib";

export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ providerId: string }> },
) {
  const { providerId } = await params;
  return proxyAgentRequest(
    request,
    `/admin-api/agent/model-providers/${encodeURIComponent(providerId)}/test`,
    "model:manage",
    { method: "POST" },
  );
}
