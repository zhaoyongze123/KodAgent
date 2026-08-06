import { NextResponse } from "next/server";
import { CLIENT_RUN_COMPLETION_DISABLED } from "@/lib/client-run-completion";

export const runtime = "nodejs";

/**
 * Run completion is an authoritative LangGraph/backend fact. Keep this
 * endpoint as an explicit tombstone for stale clients, but never let the
 * browser append a synthetic lifecycle event or forward client-supplied
 * tenant/user fields to Java.
 */
export async function POST() {
  return NextResponse.json(
    CLIENT_RUN_COMPLETION_DISABLED,
    { status: 410 },
  );
}
