export type ModelCapabilities =
  | Record<string, unknown>
  | string
  | null
  | undefined;

/** Normalize Java's JSON/string/object capability shapes at one boundary. */
export function parseModelCapabilities(
  value: ModelCapabilities,
): Record<string, unknown> {
  if (!value) return {};
  if (typeof value === "string") {
    try {
      const parsed: unknown = JSON.parse(value);
      return parsed && typeof parsed === "object"
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }
  if (typeof value.value === "string") {
    try {
      const parsed: unknown = JSON.parse(value.value);
      return parsed && typeof parsed === "object"
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }
  return value;
}

export function modelSupportsAgentTools(value: ModelCapabilities): boolean {
  const capabilities = parseModelCapabilities(value);
  return capabilities.streaming === true && capabilities.tools === true;
}
