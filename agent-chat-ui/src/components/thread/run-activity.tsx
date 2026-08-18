"use client";

/**
 * 聊天回合的运行活动区。
 *
 * 数据流：Python/Java 的运行事件 -> ProcessEvent 归并 -> 本组件。
 * 本组件只消费已经过展示边界筛选的播报和工具生命周期，不读取模型隐藏推理、
 * 路由参数或业务工具原始结果。这样“Thinking”、步骤摘要和工具状态都来自
 * 后端事实，而非前端自行编造的一段流程。
 *
 * 结构：紧凑状态行始终对应一个用户回合；有过程事件时可展开查看摘要和工具。
 * 运行时展示液态玻璃球和状态词，结束后收缩为小球，避免历史消息堆积药丸标签。
 */

import {
  AnimatePresence,
  motion,
  useInView,
  useReducedMotion,
} from "framer-motion";
import {
  Building2,
  CalendarCheck2,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  FileText,
  FolderKanban,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { LiquidThinkingOrb } from "./liquid-thinking-orb";
import { MarkdownText } from "./markdown-text";
import { normalizeProcessText, type ProcessEvent } from "./process-events";
import { formatElapsed, resolveRunActivity } from "./run-activity-state";

function toolIcon(name: string): LucideIcon {
  if (name.includes("参会人员") || name.includes("attendees")) return Users;
  if (name.includes("会议室") || name.includes("room")) return Building2;
  if (name.includes("日程") || name.includes("calendar")) return CalendarDays;
  if (
    name.includes("可预约") ||
    name.includes("冲突") ||
    name.includes("availability")
  ) {
    return CalendarCheck2;
  }
  if (name.includes("项目") || name.includes("报告") || name.includes("资料")) {
    return name.includes("项目") ? FolderKanban : FileText;
  }
  return Wrench;
}

function ThinkingCaption({ animate }: { animate: boolean }) {
  const letters = ["T", "h", "i", "n", "k", "i", "n", "g"];

  return (
    <span
      className="inline-flex items-center text-[15px] leading-none font-medium text-slate-700"
      aria-label="正在处理"
    >
      {letters.map((letter, index) => (
        <motion.span
          key={`${letter}-${index}`}
          animate={
            animate
              ? { opacity: [0.38, 1, 0.38], y: [0, -1, 0] }
              : { opacity: 0.9, y: 0 }
          }
          transition={
            animate
              ? {
                  duration: 1.55,
                  repeat: Infinity,
                  delay: index * 0.07,
                  ease: "easeInOut",
                }
              : { duration: 0.18, ease: "easeOut" }
          }
        >
          {letter}
        </motion.span>
      ))}
      <span
        aria-hidden="true"
        className="ml-1.5 inline-flex gap-1"
      >
        {[0, 1, 2].map((index) => (
          <motion.span
            key={index}
            className="size-1 rounded-full bg-slate-500"
            animate={
              animate
                ? { opacity: [0.25, 1, 0.25], y: [0, -1.5, 0] }
                : { opacity: 0.7, y: 0 }
            }
            transition={
              animate
                ? {
                    duration: 0.9,
                    repeat: Infinity,
                    delay: index * 0.14,
                    ease: "easeInOut",
                  }
                : { duration: 0.18, ease: "easeOut" }
            }
          />
        ))}
      </span>
    </span>
  );
}

function ProcessSteps({ events }: { events: readonly ProcessEvent[] }) {
  const [showAllTools, setShowAllTools] = useState(false);
  const steps = useMemo(
    () =>
      events
        .filter((event) => normalizeProcessText(event.text))
        .map((event) => ({
          ...event,
          text: normalizeProcessText(event.text),
        })),
    [events],
  );
  const toolEvents = steps.filter((event) => event.type === "tool");
  const messageEvents = steps.filter((event) => event.type === "message");
  const visibleTools =
    showAllTools || toolEvents.length <= 1 ? toolEvents : toolEvents.slice(-1);

  if (!steps.length) return null;

  return (
    <div className="mt-2 grid gap-2 border-l border-slate-200 py-1 pl-3 text-sm">
      {messageEvents.map((event, index) => (
        <div
          key={`${event.id}:${event.entryId ?? "summary"}:${index}`}
          className="text-slate-700"
        >
          <MarkdownText>{event.text}</MarkdownText>
        </div>
      ))}
      {visibleTools.length > 0 && (
        <div className="grid gap-1.5">
          {visibleTools.map((event, index) => {
            const Icon = toolIcon(event.text);
            const failed = event.status === "failed";
            const completed = event.status === "completed";
            return (
              <div
                key={`${event.id}:${event.toolCallId ?? "tool"}:${index}`}
                className="flex min-w-0 items-center gap-2 text-xs text-slate-600"
              >
                {failed ? (
                  <CircleAlert
                    aria-hidden="true"
                    className="size-3.5 shrink-0 text-red-600"
                  />
                ) : completed ? (
                  <CheckCircle2
                    aria-hidden="true"
                    className="size-3.5 shrink-0 text-emerald-600"
                  />
                ) : (
                  <Icon
                    aria-hidden="true"
                    className="size-3.5 shrink-0 text-slate-500"
                  />
                )}
                <span className="min-w-0 truncate">{event.text}</span>
                <span
                  className={cn(
                    "ml-auto shrink-0",
                    failed ? "text-red-600" : "text-slate-400",
                  )}
                >
                  {failed ? "失败" : completed ? "已完成" : "进行中"}
                </span>
              </div>
            );
          })}
          {toolEvents.length > 1 && (
            <button
              type="button"
              onClick={() => setShowAllTools((value) => !value)}
              className="w-fit text-xs text-slate-500 hover:text-slate-800"
            >
              {showAllTools
                ? "收起工具步骤"
                : `查看其余 ${toolEvents.length - 1} 个工具步骤`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function RunActivity({
  events,
  elapsedSeconds,
  hidden,
  isRunning,
  syncError,
}: {
  events: readonly ProcessEvent[];
  elapsedSeconds: number;
  hidden: boolean;
  isRunning: boolean;
  syncError?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const inView = useInView(rootRef, { amount: 0.1 });
  const reducedMotion = useReducedMotion();
  const [isOpen, setIsOpen] = useState(isRunning);
  const phase = resolveRunActivity(events, isRunning);
  const hasDetails = events.some((event) => normalizeProcessText(event.text));

  useEffect(() => {
    setIsOpen(isRunning);
  }, [isRunning]);

  if (hidden) return null;

  return (
    <div
      ref={rootRef}
      className="mx-auto w-full max-w-3xl py-1"
    >
      <button
        type="button"
        aria-expanded={hasDetails ? isOpen : undefined}
        aria-controls={hasDetails ? "run-activity-details" : undefined}
        aria-label={hasDetails ? "展开或收起本次处理过程" : "当前处理状态"}
        onClick={() => hasDetails && setIsOpen((open) => !open)}
        className={cn(
          "flex min-h-8 w-full items-center gap-2 text-left text-xs text-slate-500",
          hasDetails && "cursor-pointer hover:text-slate-700",
        )}
      >
        <AnimatePresence
          initial={false}
          mode="wait"
        >
          {isRunning ? (
            <motion.span
              key="running"
              className="inline-flex h-12 shrink-0 items-center gap-3 rounded-full border border-slate-200 bg-white px-2.5 pr-4 shadow-[inset_0_1px_0_rgb(255_255_255_/_0.95)]"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.72 }}
              transition={{
                duration: reducedMotion ? 0 : 0.18,
                ease: "easeOut",
              }}
            >
              <LiquidThinkingOrb
                fullSize
                failed={phase.tone === "failed"}
                animate={inView && !reducedMotion}
              />
              <ThinkingCaption
                animate={inView && !reducedMotion && phase.tone !== "failed"}
              />
            </motion.span>
          ) : (
            <motion.span
              key="completed"
              className="ml-2.5 inline-flex size-10 shrink-0 items-center justify-center"
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{
                duration: reducedMotion ? 0 : 0.18,
                ease: "easeOut",
              }}
            >
              <LiquidThinkingOrb
                fullSize
                failed={phase.tone === "failed"}
                animate={inView && !reducedMotion}
              />
            </motion.span>
          )}
        </AnimatePresence>
        <span className="shrink-0 tabular-nums">
          已处理 {formatElapsed(elapsedSeconds)}
        </span>
        {syncError && isRunning && (
          <span
            className="min-w-0 truncate text-amber-600"
            title={syncError}
          >
            过程事件同步失败
          </span>
        )}
        {hasDetails && (
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "size-3.5 transition-transform",
              isOpen && "rotate-90",
            )}
          />
        )}
      </button>
      {hasDetails && isOpen && (
        <div id="run-activity-details">
          <ProcessSteps events={events} />
        </div>
      )}
    </div>
  );
}
