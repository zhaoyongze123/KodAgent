import { proxyAgentRequest, readJsonBody } from "../_lib";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return proxyAgentRequest(request, "/admin-api/agent/model-bindings", "model:read");
}

export async function POST(request: Request) {
  return proxyAgentRequest(request, "/admin-api/agent/model-bindings", "model:manage", {
    method: "POST",
    body: JSON.stringify(await readJsonBody(request)),
  });
}
