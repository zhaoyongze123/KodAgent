/**
 * AssistantMessage 的展示契约解析。
 *
 * 聊天状态中同时保存最终回答、工具协议和代码控制消息；它们都可能是 AIMessage。
 * 本模块只解析后端写入 additional_kwargs.kodagentPresentation 的受限元数据，供
 * 流式交接、消息投影和卡片渲染共享。它不读取模型正文、不推断业务状态，也不负责
 * UI 渲染，确保“是否可展示”的事实只在一个边界定义。
 *
 * v2 是当前契约：internal 永不展示为正文，final 是唯一可提交的普通回答，card
 * 是结构化界面块。v1 仅保留项目报告卡片的历史回放兼容。
 */

export type GeneratedAttachment = {
  artifactId: string;
  title: string;
  filename: string;
  format: "DOCX" | "XLSX";
  mimeType?: string;
  size?: number;
};

export type AssistantPresentationV2 =
  | { schemaVersion: 2; kind: "internal" }
  | {
      schemaVersion: 2;
      kind: "final";
      finalEntryId: string;
      attachments?: GeneratedAttachment[];
    }
  | {
      schemaVersion: 2;
      kind: "card";
      cardType: string;
      payload: Record<string, unknown>;
    };

export type AssistantPresentationV1Card = {
  schemaVersion: 1;
  blockType: "card";
  cardType: string;
  payload: Record<string, unknown>;
};

export type AssistantMessagePresentation =
  | AssistantPresentationV2
  | AssistantPresentationV1Card;

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : undefined;
}

function attachments(value: unknown): GeneratedAttachment[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const result: GeneratedAttachment[] = [];
  for (const raw of value) {
    const item = record(raw);
    const artifactId = typeof item?.artifactId === "string" ? item.artifactId : "";
    const format = typeof item?.format === "string" ? item.format.toUpperCase() : "";
    const filename = typeof item?.filename === "string" ? item.filename : "";
    const title = typeof item?.title === "string" ? item.title : "";
    if (!/^[0-9a-f-]{16,80}$/i.test(artifactId) || !["DOCX", "XLSX"].includes(format) || !filename || !title) continue;
    result.push({
      artifactId,
      title,
      filename,
      format: format as GeneratedAttachment["format"],
      mimeType: typeof item?.mimeType === "string" ? item.mimeType : undefined,
      size: typeof item?.size === "number" && item.size >= 0 ? item.size : undefined,
    });
  }
  return result.length ? result : undefined;
}

/** Return the raw presentation record when the backend attached one. */
export function rawAssistantMessagePresentation(
  message: unknown,
): Record<string, unknown> | undefined {
  const messageRecord = record(message);
  const additional = record(messageRecord?.additional_kwargs);
  return record(additional?.kodagentPresentation);
}

/**
 * Parse a recognized presentation shape. An unrecognized record deliberately
 * returns undefined; callers must still use rawAssistantMessagePresentation to
 * distinguish malformed current metadata from a genuinely legacy message.
 */
export function assistantMessagePresentation(
  message: unknown,
): AssistantMessagePresentation | undefined {
  const value = rawAssistantMessagePresentation(message);
  if (!value) return undefined;

  if (value.schemaVersion === 2) {
    if (value.kind === "internal") {
      return { schemaVersion: 2, kind: "internal" };
    }
    if (
      value.kind === "final" &&
      typeof value.finalEntryId === "string" &&
      value.finalEntryId.length > 0
    ) {
      return {
        schemaVersion: 2,
        kind: "final",
        finalEntryId: value.finalEntryId,
        attachments: attachments(value.attachments),
      };
    }
    if (
      value.kind === "card" &&
      typeof value.cardType === "string" &&
      value.cardType.length > 0 &&
      record(value.payload)
    ) {
      return {
        schemaVersion: 2,
        kind: "card",
        cardType: value.cardType,
        payload: record(value.payload)!,
      };
    }
    return undefined;
  }

  if (
    value.schemaVersion === 1 &&
    value.blockType === "card" &&
    typeof value.cardType === "string" &&
    value.cardType.length > 0 &&
    record(value.payload)
  ) {
    return {
      schemaVersion: 1,
      blockType: "card",
      cardType: value.cardType,
      payload: record(value.payload)!,
    };
  }
  return undefined;
}

export function attachmentsFromAssistantMessage(message: unknown): GeneratedAttachment[] {
  const presentation = assistantMessagePresentation(message);
  return presentation?.schemaVersion === 2 && presentation.kind === "final"
    ? presentation.attachments ?? []
    : [];
}

export function finalEntryIdFromAssistantMessage(
  message: unknown,
): string | undefined {
  const presentation = assistantMessagePresentation(message);
  return presentation?.schemaVersion === 2 && presentation.kind === "final"
    ? presentation.finalEntryId
    : undefined;
}

export function isInternalAssistantPresentation(message: unknown): boolean {
  const presentation = assistantMessagePresentation(message);
  return presentation?.schemaVersion === 2 && presentation.kind === "internal";
}

export function isFinalAssistantPresentation(message: unknown): boolean {
  return finalEntryIdFromAssistantMessage(message) !== undefined;
}

export function isCardAssistantPresentation(message: unknown): boolean {
  const presentation = assistantMessagePresentation(message);
  return presentation?.schemaVersion === 2
    ? presentation.kind === "card"
    : presentation?.schemaVersion === 1;
}
