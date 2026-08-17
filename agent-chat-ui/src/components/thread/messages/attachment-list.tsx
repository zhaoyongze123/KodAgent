"use client";

import { useState } from "react";
import { Download, Eye, FileSpreadsheet, FileText } from "lucide-react";

import { TooltipIconButton } from "@/components/thread/tooltip-icon-button";
import { isPreviewableArtifact } from "@/lib/artifact-preview";
import type { GeneratedAttachment } from "@/lib/assistant-message-presentation";
import { AttachmentPreviewSheet } from "./attachment-preview-sheet";

function sizeLabel(size?: number): string | undefined {
  if (typeof size !== "number") return undefined;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** 最终回答下方的受控文件列表；下载地址只由 artifactId 重建。 */
export function AttachmentList({
  attachments,
}: {
  attachments: GeneratedAttachment[];
}) {
  const [previewing, setPreviewing] = useState<GeneratedAttachment>();
  if (!attachments.length) return null;
  return (
    <>
      <div className="divide-border border-border bg-background mt-2 flex max-w-full flex-col divide-y overflow-hidden rounded-md border">
        {attachments.map((attachment) => {
          const Icon =
            attachment.format === "XLSX" ? FileSpreadsheet : FileText;
          const meta = [attachment.format, sizeLabel(attachment.size)]
            .filter(Boolean)
            .join(" · ");
          return (
            <div
              key={attachment.artifactId}
              className="group hover:bg-muted/50 flex min-h-12 items-center gap-2.5 px-3 py-2 text-left transition-colors"
            >
              <Icon
                className="text-muted-foreground size-4 shrink-0"
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1">
                <span className="text-foreground block truncate text-sm font-medium">
                  {attachment.title}
                </span>
                <span className="text-muted-foreground block truncate text-xs">
                  {attachment.filename}
                  {meta ? ` · ${meta}` : ""}
                </span>
              </span>
              {isPreviewableArtifact(attachment) && (
                <TooltipIconButton
                  type="button"
                  tooltip="预览附件"
                  aria-label={`预览 ${attachment.filename}`}
                  onClick={() => setPreviewing(attachment)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <Eye
                    className="size-4"
                    aria-hidden="true"
                  />
                </TooltipIconButton>
              )}
              <a
                href={`/api/artifacts/${encodeURIComponent(attachment.artifactId)}`}
                download={attachment.filename}
                className="text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring flex size-6 shrink-0 items-center justify-center rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
                aria-label={`下载 ${attachment.filename}`}
                title="下载附件"
              >
                <Download
                  className="size-4"
                  aria-hidden="true"
                />
              </a>
            </div>
          );
        })}
      </div>
      <AttachmentPreviewSheet
        attachment={previewing}
        onOpenChange={(open) => {
          if (!open) setPreviewing(undefined);
        }}
      />
    </>
  );
}
