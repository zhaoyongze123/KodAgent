export type ProjectKnowledgeEvidence = {
  citationId: string;
  name: string;
  sourceType: string;
  section: string;
  contentVersion: string;
  retrievalMethod: string;
  excerpt: string;
};

function value(input: unknown, fallback: string) {
  const normalized = input == null ? "" : String(input).trim();
  return normalized || fallback;
}

/**
 * Project knowledge search returns an EvidenceSet, not an indexed document.
 * Keep this projection at the UI boundary so legacy checkpoint fields cannot
 * accidentally expose chunk IDs, scores, file paths, or the full text.
 */
export function projectKnowledgeEvidence(
  hit: Record<string, unknown>,
): ProjectKnowledgeEvidence {
  return {
    citationId: value(hit.citationId, "资料"),
    name: value(hit.name, "未命名资料"),
    sourceType: value(hit.sourceType, ""),
    section: value(hit.section, "未标注章节"),
    contentVersion: value(hit.contentVersion, "未标注版本"),
    retrievalMethod: value(hit.retrievalMethod, "keyword"),
    excerpt: value(hit.excerpt, "暂无可展示的资料摘要。"),
  };
}
