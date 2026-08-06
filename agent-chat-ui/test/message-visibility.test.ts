import assert from "node:assert/strict";
import test from "node:test";
import type { Message } from "@langchain/langgraph-sdk";
import {
  isProcessOnlyToolName,
  isProcessOnlyToolMessage,
  isRenderableAssistantMessage,
} from "../src/components/thread/messages/message-visibility.ts";

const asMessage = (value: Record<string, unknown>) => value as Message;

test("structured process-only tools are excluded from ordinary chat rendering", () => {
  for (const name of [
    "report_progress",
    "task",
    "route_conversation",
  ]) {
    assert.equal(isProcessOnlyToolName(name), true);
    const message = asMessage({
      id: `${name}-result`,
      type: "tool",
      name,
      content: "结构化过程事件已记录",
      tool_call_id: `${name}-call`,
    });

    assert.equal(isProcessOnlyToolMessage(message), true);
    assert.equal(isRenderableAssistantMessage(message), false);
  }
});

test("real business tools remain ordinary renderable results", () => {
  for (const name of [
    "list_available_meeting_rooms",
    "get_meeting_attendees_calendar",
    "check_meeting_availability",
    "get_my_calendar",
    "search_party_files",
  ]) {
    assert.equal(isProcessOnlyToolName(name), false);
    assert.equal(
      isRenderableAssistantMessage(
        asMessage({
          id: `${name}-result`,
          type: "tool",
          name,
          content: '{"ok":true,"data":{"items":[]}}',
          tool_call_id: `${name}-call`,
        }),
      ),
      true,
    );
  }
});

test("real business tool errors remain renderable", () => {
  assert.equal(
    isRenderableAssistantMessage(
      asMessage({
        id: "calendar-error",
        type: "tool",
        name: "get_my_calendar",
        status: "error",
        content:
          '{"ok":false,"error":{"code":"SCHEDULE_FACADE_UNAVAILABLE","message":"日历暂时不可用"}}',
        tool_call_id: "calendar-error-call",
      }),
    ),
    true,
  );
});

test("empty AI and Tool results do not mount an outer message row", () => {
  assert.equal(
    isRenderableAssistantMessage(
      asMessage({ id: "empty-ai", type: "ai", content: " \n" }),
    ),
    false,
  );
  assert.equal(
    isRenderableAssistantMessage(
      asMessage({
        id: "empty-tool",
        type: "tool",
        name: "route_conversation",
        content: "\u200B\n",
        tool_call_id: "route-call",
      }),
    ),
    false,
  );
});

test("ordinary AI narration and real tool results remain renderable", () => {
  assert.equal(
    isRenderableAssistantMessage(
      asMessage({ id: "ai", type: "ai", content: "已完成查询" }),
    ),
    true,
  );
  assert.equal(
    isRenderableAssistantMessage(
      asMessage({
        id: "tool",
        type: "tool",
        name: "get_my_calendar",
        content: '{"ok":true}',
        tool_call_id: "calendar-call",
      }),
    ),
    true,
  );
});
