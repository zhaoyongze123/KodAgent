export type KnowledgeSourceKind = "KOD_FOLDER" | "LOCAL_UPLOAD";

export const knowledgeManagementPermission = "knowledge:manage";

export function accessLabel(kind: string, mode: string): string {
  if (kind === "KOD_FOLDER") return "按 KodCloud 文件夹权限";
  return mode === "ALL" ? "全员可检索" : "指定部门和人员";
}

export function libraryStatus(status: string, lastSyncStatus?: string | null): string {
  if (status === "DISABLED") return "已停用";
  if (lastSyncStatus === "FAILED") return "同步失败";
  if (lastSyncStatus === "SUCCEEDED") return "可检索";
  return "待同步";
}

export function normalizeAclSelection(users: string[], departments: string[]) {
  const numbers = (values: string[]) =>
    [...new Set(values.map((value) => Number(value)).filter((value) => Number.isInteger(value) && value > 0))];
  return { userIds: numbers(users), departmentIds: numbers(departments) };
}
