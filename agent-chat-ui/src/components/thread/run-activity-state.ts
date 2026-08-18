/**
 * 运行活动区的纯状态归并。
 *
 * 输入仅为经过 ``process-events`` 规范化的服务端事件与运行状态，输出是聊天 UI
 * 可以展示的状态词。该文件不依赖 React，便于单测并避免页面组件自行维护一套
 * 与后端事件脱节的布尔状态。
 */

import { normalizeProcessText, type ProcessEvent } from "./process-events.ts";

export type ActivityPhase = {
  tone: "working" | "failed" | "completed";
};

export function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remainingSeconds}s` : `${remainingSeconds}s`;
}

/** 从事件末尾推导当前状态，绝不根据前端计时器伪造业务步骤。 */
export function resolveRunActivity(
  events: readonly ProcessEvent[],
  isRunning: boolean,
): ActivityPhase {
  const visible = events.filter((event) => normalizeProcessText(event.text));
  const latest = visible.at(-1);

  if (!isRunning) {
    return {
      tone: latest?.status === "failed" ? "failed" : "completed",
    };
  }

  if (latest?.type === "tool") {
    if (latest.status === "failed") {
      return { tone: "failed" };
    }
  }

  // 过程正文只展示模型摘要和工具信息；液态球只消费运行语义，不能再派生
  // “Thinking”等固定状态词，以免与真实过程摘要竞争展示空间。
  return { tone: "working" };
}
