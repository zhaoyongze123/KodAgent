import { proxyKnowledgeRequest } from "../../_lib";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const folderId = url.searchParams.get("folderId");
  const query = folderId && /^\d+$/.test(folderId) ? `?folderId=${encodeURIComponent(folderId)}` : "";
  return proxyKnowledgeRequest(request, `/admin-api/agent/knowledge-libraries/kod-folders/browse${query}`);
}
