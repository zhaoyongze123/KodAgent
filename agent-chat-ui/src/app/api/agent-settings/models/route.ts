import { proxyAgentRequest } from "../_lib";

export const runtime = "nodejs";

export async function GET(request: Request) {
  return proxyAgentRequest(request, "/admin-api/agent/models", "model:read");
}
