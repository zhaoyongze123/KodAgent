import { CheckCircle2, Download, Eye, FileText, Paperclip } from "lucide-react";
import { partyFileAttachmentPath } from "@/lib/party-file-attachment";
import { displayFieldValue, displayStatus } from "@/lib/card-display";
import type { PartyFilePayload } from "@/types/agent-block";

function shortTime(value?: string) {
  return value ? value.replace("T", " ").slice(0, 16) : "";
}

function plainText(value?: string) {
  return value
    ?.replace(/<br\s*\/?>(\r?\n)?/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/gi, " ")
    .trim();
}

function formatSize(size?: number) {
  if (typeof size !== "number" || size < 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function PartyFileCard({ payload }: { payload: PartyFilePayload }) {
  const items = payload.items ?? [];
  const isDetail = payload.view === "detail" || payload.view === "attachments";
  const isAttachmentView = payload.view === "attachments";
  return (
    <div className="border-border bg-card my-2 w-full max-w-xl rounded-xl border p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-800">
        <FileText className="size-5 text-slate-600" aria-hidden="true" />
        <span>{isAttachmentView ? "党务文件附件" : isDetail ? "党务文件详情" : "党务文件"}</span>
        <span className="text-muted-foreground ml-auto text-xs font-normal">
          {isAttachmentView ? "已核对附件" : isDetail ? "已记录阅读" : `共 ${payload.total} 条`}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="border-border text-muted-foreground rounded-lg border border-dashed px-4 py-6 text-center text-sm">
          没有找到匹配的党务文件
        </div>
      ) : (
        <ol className="grid gap-2.5">
          {items.map((item, index) => (
            <li
              key={item.id ?? `${item.title ?? "file"}-${index}`}
              className="border-border/70 bg-muted/30 rounded-lg border p-3"
            >
              <div className="flex items-start gap-2">
                <FileText
                  className="text-muted-foreground mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-foreground text-sm font-medium">
                    {item.title || "未命名文件"}
                  </div>
                  <div className="text-muted-foreground mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                    {(item.categoryName || item.categoryId) && <span>分类：{displayFieldValue("分类", item.categoryName ?? item.categoryId, { domain: "party_file" })}</span>}
                    {item.publishTime && <span>{shortTime(item.publishTime)}</span>}
                    {item.status && <span>状态：{displayStatus(item.status, { domain: "party_file" })}</span>}
                    {item.readStatus && (
                      <span className="inline-flex items-center gap-1">
                        <CheckCircle2 className="size-3" aria-hidden="true" />
                        已读
                      </span>
                    )}
                  </div>
                  {item.summary && (
                    <p className="text-muted-foreground mt-2 line-clamp-2 text-xs leading-5">
                      {item.summary}
                    </p>
                  )}
                  {isDetail && plainText(item.content) && (
                    <p className="text-foreground mt-3 whitespace-pre-wrap text-sm leading-6">
                      {plainText(item.content)}
                    </p>
                  )}
                  {isAttachmentView && item.attachmentMessage && (
                    <p className="text-muted-foreground mt-3 text-xs leading-5">
                      {item.attachmentMessage}
                    </p>
                  )}
                  {isDetail && item.attachments && item.attachments.length > 0 && (
                    <div className="mt-4 grid gap-2 border-t pt-3">
                      <span className="text-muted-foreground text-xs font-medium">
                        附件
                      </span>
                      {item.attachments.map((attachment, attachmentIndex) => {
                        const attachmentId = attachment.id;
                        const fileId = item.id;
                        const canOpen = Boolean(fileId && attachmentId);
                        return (
                          <div
                            key={attachmentId ?? `${attachment.name ?? "attachment"}-${attachmentIndex}`}
                            className="bg-background flex flex-wrap items-center gap-2 rounded-md border px-2.5 py-2"
                          >
                            <Paperclip className="text-muted-foreground size-3.5 shrink-0" aria-hidden="true" />
                            <span className="min-w-0 flex-1 truncate text-xs text-slate-700">
                              {attachment.name || "未命名附件"}
                            </span>
                            {(attachment.type || formatSize(attachment.size)) && (
                              <span className="text-muted-foreground text-[11px]">
                                {[attachment.type, formatSize(attachment.size)]
                                  .filter(Boolean)
                                  .join(" · ")}
                              </span>
                            )}
                            {canOpen && (
                              <>
                                <a
                                  className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
                                  href={partyFileAttachmentPath(fileId!, attachmentId!, "preview")}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  <Eye className="size-3.5" aria-hidden="true" />
                                  预览
                                </a>
                                <a
                                  className="text-primary inline-flex items-center gap-1 text-xs hover:underline"
                                  href={partyFileAttachmentPath(fileId!, attachmentId!, "download")}
                                >
                                  <Download className="size-3.5" aria-hidden="true" />
                                  下载
                                </a>
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {isAttachmentView && (!item.attachments || item.attachments.length === 0) && (
                    <div className="border-border text-muted-foreground mt-4 rounded-md border border-dashed px-3 py-3 text-xs">
                      当前文件没有附件
                    </div>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
