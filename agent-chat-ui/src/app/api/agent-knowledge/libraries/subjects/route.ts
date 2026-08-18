import { proxyKnowledgeRequest } from "../../_lib";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const kind = url.searchParams.get("kind") === "departments" ? "departments" : "users";
  const keyword = url.searchParams.get("keyword") ?? "";
  return proxyKnowledgeRequest(
    request,
    `/admin-api/agent/knowledge-libraries/subjects?kind=${kind}&keyword=${encodeURIComponent(keyword)}`,
  );
}
