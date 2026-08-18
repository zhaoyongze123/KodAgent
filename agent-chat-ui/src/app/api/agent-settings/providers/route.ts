import { proxyAgentRequest, readJsonBody } from "../_lib";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return proxyAgentRequest(request, "/admin-api/agent/model-providers", "model:read");
}

export async function POST(request: Request) {
  return proxyAgentRequest(request, "/admin-api/agent/model-providers", "model:manage", {
    method: "POST",
    body: JSON.stringify(await readJsonBody(request)),
  });
}
