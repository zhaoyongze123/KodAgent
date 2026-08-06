import assert from "node:assert/strict";
import test from "node:test";
import { partyFilePayloadFromData } from "../src/types/agent-block.ts";
import { partyFileAttachmentPath } from "../src/lib/party-file-attachment.ts";

test("party file detail turns one safe Tool response into a detail card", () => {
  const payload = partyFilePayloadFromData({
    id: 8,
    title: "组织生活通知",
    content: "请参会",
    attachments: [{ id: 51, name: "通知.pdf", type: "application/pdf", size: 2048 }],
  });

  assert.deepEqual(payload, {
    total: 1,
    view: "detail",
    items: [
      {
        id: "8",
        title: "组织生活通知",
        content: "请参会",
        attachments: [{ id: "51", name: "通知.pdf", type: "application/pdf", size: 2048 }],
      },
    ],
  });
});

test("attachment links stay on the authenticated same-origin proxy", () => {
  const preview = partyFileAttachmentPath("8", "51", "preview");
  const download = partyFileAttachmentPath("8", "51", "download");

  assert.equal(preview, "/api/party-files/8/attachments/51?action=preview");
  assert.equal(download, "/api/party-files/8/attachments/51?action=download");
  assert.doesNotMatch(preview, /https?:\/\//);
});

test("attachment inspection renders an explicit no-attachment state", () => {
  const payload = partyFilePayloadFromData({
    id: 9,
    title: "无附件通知",
    attachmentStatus: "NONE",
    attachmentCount: 0,
    attachmentMessage: "该文件没有附件。",
    attachments: [],
  });

  assert.deepEqual(payload, {
    total: 1,
    view: "attachments",
    items: [
      {
        id: "9",
        title: "无附件通知",
        attachments: [],
        attachmentStatus: "NONE",
        attachmentCount: 0,
        attachmentMessage: "该文件没有附件。",
      },
    ],
  });
});
