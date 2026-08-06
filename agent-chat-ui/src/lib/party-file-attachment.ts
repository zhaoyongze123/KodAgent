/**
 * Attachment bytes never appear in an Agent Tool response. The browser reaches
 * this same-origin endpoint with its HttpOnly identity cookie; Next forwards
 * it to Java, which checks current visibility and file ownership.
 */
export function partyFileAttachmentPath(
  partyFileId: string,
  attachmentId: string,
  action: "preview" | "download",
) {
  return `/api/party-files/${encodeURIComponent(partyFileId)}/attachments/${encodeURIComponent(attachmentId)}?action=${action}`;
}
