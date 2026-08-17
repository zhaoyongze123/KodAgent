import assert from "node:assert/strict";
import test from "node:test";
import { projectKnowledgeEvidence } from "../src/lib/project-knowledge-evidence.ts";

test("projects only safe evidence fields for the project knowledge card", () => {
  const evidence = projectKnowledgeEvidence({
    citationId: "资料 2",
    name: "综合交通提升规划任务书.docx",
    sourceType: "PROJECT_FILES",
    section: "第 3 章 工作内容",
    contentVersion: "v20260817",
    retrievalMethod: "hybrid",
    excerpt: "停车组织与施工期交通保障应形成专项建议。",
    chunkId: 99,
    fileId: 88,
    fusionScore: 0.123,
    content: "The card must not receive the full indexed text.",
  });

  assert.deepEqual(evidence, {
    citationId: "资料 2",
    name: "综合交通提升规划任务书.docx",
    sourceType: "PROJECT_FILES",
    section: "第 3 章 工作内容",
    contentVersion: "v20260817",
    retrievalMethod: "hybrid",
    excerpt: "停车组织与施工期交通保障应形成专项建议。",
  });
});

test("uses explicit placeholders when an older persisted evidence item is incomplete", () => {
  assert.deepEqual(projectKnowledgeEvidence({ name: "旧资料" }), {
    citationId: "资料",
    name: "旧资料",
    sourceType: "",
    section: "未标注章节",
    contentVersion: "未标注版本",
    retrievalMethod: "keyword",
    excerpt: "暂无可展示的资料摘要。",
  });
});
