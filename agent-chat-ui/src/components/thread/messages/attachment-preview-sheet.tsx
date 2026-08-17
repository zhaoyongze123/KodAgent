"use client";

import { useEffect, useState } from "react";
import {
  Download,
  FileSpreadsheet,
  FileText,
  LoaderCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { artifactPreviewPath } from "@/lib/artifact-preview";
import type { GeneratedAttachment } from "@/lib/assistant-message-presentation";

function sizeLabel(size?: number): string | undefined {
  if (typeof size !== "number") return undefined;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function failureMessage(response: Response): Promise<string> {
  return response
    .json()
    .then((value: { error?: unknown }) =>
      typeof value.error === "string" ? value.error : "附件预览暂不可用",
    )
    .catch(() => "附件预览暂不可用");
}

/**
 * 附件预览的唯一状态拥有者。它只消费同源预览 HTML，不了解模型消息、附件存储或
 * Java 授权细节，因此列表关闭或替换选中附件时不会遗留跨消息展示状态。
 */
export function AttachmentPreviewSheet({
  attachment,
  onOpenChange,
}: {
  attachment?: GeneratedAttachment;
  onOpenChange: (open: boolean) => void;
}) {
  const [html, setHtml] = useState<string>();
  const [error, setError] = useState<string>();
  const artifactId = attachment?.artifactId;

  useEffect(() => {
    if (!artifactId) {
      setHtml(undefined);
      setError(undefined);
      return;
    }
    const controller = new AbortController();
    setHtml(undefined);
    setError(undefined);
    void fetch(artifactPreviewPath(artifactId), {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await failureMessage(response));
        return response.text();
      })
      .then((nextHtml) => {
        if (!controller.signal.aborted) setHtml(nextHtml);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "附件预览暂不可用");
      });
    return () => controller.abort();
  }, [artifactId]);

  const Icon = attachment?.format === "XLSX" ? FileSpreadsheet : FileText;
  const meta = attachment
    ? [attachment.format, sizeLabel(attachment.size)]
        .filter(Boolean)
        .join(" · ")
    : "";

  return (
    <Sheet
      open={Boolean(attachment)}
      onOpenChange={onOpenChange}
    >
      <SheetContent
        side="right"
        className="w-[min(52rem,calc(100vw-1rem))] max-w-none gap-0 p-0 sm:max-w-none"
      >
        {attachment && (
          <>
            <SheetHeader className="border-border shrink-0 border-b pr-12">
              <SheetTitle className="flex min-w-0 items-center gap-2 text-base">
                <Icon
                  className="text-muted-foreground size-4 shrink-0"
                  aria-hidden="true"
                />
                <span className="truncate">{attachment.title}</span>
              </SheetTitle>
              <SheetDescription className="truncate">
                {attachment.filename}
                {meta ? ` · ${meta}` : ""}
              </SheetDescription>
            </SheetHeader>
            <div className="bg-muted/20 min-h-0 flex-1">
              {html ? (
                <iframe
                  title={`${attachment.title} 预览`}
                  srcDoc={html}
                  sandbox=""
                  className="bg-background h-full w-full border-0"
                />
              ) : error ? (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
                  <p className="text-muted-foreground text-sm">{error}</p>
                  <Button
                    asChild
                    size="sm"
                    variant="outline"
                  >
                    <a
                      href={`/api/artifacts/${encodeURIComponent(attachment.artifactId)}`}
                      download={attachment.filename}
                    >
                      <Download
                        className="size-3.5"
                        aria-hidden="true"
                      />
                      下载附件
                    </a>
                  </Button>
                </div>
              ) : (
                <div className="text-muted-foreground flex h-full items-center justify-center gap-2 text-sm">
                  <LoaderCircle
                    className="size-4 animate-spin"
                    aria-hidden="true"
                  />
                  正在加载预览
                </div>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
