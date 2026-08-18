import { NextResponse } from "next/server";

import { proxyKnowledgeRequest } from "../../../_lib";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ libraryId: string }> },
) {
  const { libraryId } = await params;
  if (!/^\d+$/.test(libraryId) || Number(libraryId) <= 0) {
    return NextResponse.json({ error: "知识源编号无效" }, { status: 400 });
  }
  return proxyKnowledgeRequest(
    request,
    `/admin-api/agent/knowledge-libraries/${encodeURIComponent(libraryId)}/sync`,
    { method: "POST" },
  );
}
