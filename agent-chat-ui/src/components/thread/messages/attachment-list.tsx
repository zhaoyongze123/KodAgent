"use client";

import { Download, FileSpreadsheet, FileText } from "lucide-react";
import type { GeneratedAttachment } from "@/lib/assistant-message-presentation";

function sizeLabel(size?: number): string | undefined {
  if (typeof size !== "number") return undefined;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** 最终回答下方的受控文件列表；下载地址只由 artifactId 重建。 */
export function AttachmentList({ attachments }: { attachments: GeneratedAttachment[] }) {
  if (!attachments.length) return null;
  return (
    <div className="mt-2 flex max-w-full flex-col divide-y divide-border overflow-hidden rounded-md border border-border bg-background">
      {attachments.map((attachment) => {
        const Icon = attachment.format === "XLSX" ? FileSpreadsheet : FileText;
        const meta = [attachment.format, sizeLabel(attachment.size)].filter(Boolean).join(" · ");
        return (
          <a
            key={attachment.artifactId}
            href={`/api/artifacts/${encodeURIComponent(attachment.artifactId)}`}
            download={attachment.filename}
            className="group flex min-h-12 items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`下载 ${attachment.filename}`}
          >
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-foreground">{attachment.title}</span>
              <span className="block truncate text-xs text-muted-foreground">{attachment.filename}{meta ? ` · ${meta}` : ""}</span>
            </span>
            <Download className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden="true" />
          </a>
        );
      })}
    </div>
  );
}
