import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace SystemNotifyMessageApi {
  export type NotifyTemplateParams = Record<string, any>;

  /** 站内信消息信息 */
  export interface NotifyMessage {
    id: number;
    userId: number;
    userType: number;
    templateId: number;
    templateCode: string;
    templateNickname: string;
    templateContent: string;
    templateType: number;
    templateParams: NotifyTemplateParams;
    readStatus: boolean;
    readTime: Date;
    createTime: Date;
  }
}

export function extractNoticeId(
  message?: Pick<SystemNotifyMessageApi.NotifyMessage, 'templateCode' | 'templateParams'>,
) {
  if (!message || message.templateCode !== 'system_notice_push') {
    return undefined;
  }
  const noticeId = message.templateParams?.noticeId;
  if (noticeId === undefined || noticeId === null || noticeId === '') {
    return undefined;
  }
  const parsed = Number(noticeId);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** 查询站内信消息列表 */
export function getNotifyMessagePage(params: PageParam) {
  return requestClient.get<PageResult<SystemNotifyMessageApi.NotifyMessage>>(
    '/system/notify-message/page',
    { params },
  );
}

/** 获得我的站内信分页 */
export function getMyNotifyMessagePage(params: PageParam) {
  return requestClient.get<PageResult<SystemNotifyMessageApi.NotifyMessage>>(
    '/system/notify-message/my-page',
    { params },
  );
}

/** 批量标记已读 */
export function updateNotifyMessageRead(ids: number[]) {
  return requestClient.put(
    '/system/notify-message/update-read',
    {},
    {
      params: { ids },
    },
  );
}

/** 标记所有站内信为已读 */
export function updateAllNotifyMessageRead() {
  return requestClient.put('/system/notify-message/update-all-read');
}

/** 获取当前用户的最新站内信列表 */
export function getUnreadNotifyMessageList() {
  return requestClient.get<SystemNotifyMessageApi.NotifyMessage[]>(
    '/system/notify-message/get-unread-list',
  );
}

/** 获得当前用户的未读站内信数量 */
export function getUnreadNotifyMessageCount() {
  return requestClient.get<number>('/system/notify-message/get-unread-count');
}
