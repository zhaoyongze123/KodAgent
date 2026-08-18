import { proxyKnowledgeRequest } from "../_lib";

export async function GET(request: Request) {
  return proxyKnowledgeRequest(request, "/admin-api/agent/knowledge-libraries");
}

export async function POST(request: Request) {
  return proxyKnowledgeRequest(request, "/admin-api/agent/knowledge-libraries/kod-folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
