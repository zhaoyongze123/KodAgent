type ArtifactPreviewTarget = {
  artifactId: string;
  format: string;
};

/** 预览地址只能由服务端签发的 artifactId 构建，不能信任模型提供的任意 URL。 */
export function artifactPreviewPath(artifactId: string): string {
  return `/api/artifacts/${encodeURIComponent(artifactId)}/preview`;
}

/** 当前附件生成器仅产出这两种 OOXML 文件，均由 Java 转为受控只读 HTML。 */
export function isPreviewableArtifact(
  artifact: ArtifactPreviewTarget,
): boolean {
  return artifact.format === "DOCX" || artifact.format === "XLSX";
}
