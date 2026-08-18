import type { RouteLocationRaw } from 'vue-router';

import type { SystemNotifyMessageApi } from '#/api/system/notify/message';

import { extractNoticeId } from '#/api/system/notify/message';

type NotificationTone = 'danger' | 'info' | 'success' | 'warning';

interface NotificationField {
  label: string;
  value: string;
}

interface NotificationAction {
  label: string;
  to?: RouteLocationRaw;
  url?: string;
}

interface NotificationPresentation {
  action?: NotificationAction;
  body: string[];
  bodyTitle: string;
  fields: NotificationField[];
  preview: string;
  statusLabel: string;
  subtitle: string;
  title: string;
  tone: NotificationTone;
}

const BPM_TASK_ASSIGNED_CODE = 'bpm_task_assigned';
const BPM_PROCESS_APPROVE_CODE = 'bpm_process_instance_approve';
const BPM_PROCESS_REJECT_CODE = 'bpm_process_instance_reject';

function resolveWorkbenchDetailSection(templateCode?: string) {
  return templateCode === BPM_TASK_ASSIGNED_CODE ? 'pending' : 'initiated';
}

function stripHtmlContent(value?: string) {
  if (!value) {
    return '';
  }
  return value
    .replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeText(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function resolveProcessDetailRoute(
  message: Pick<SystemNotifyMessageApi.NotifyMessage, 'templateCode' | 'templateParams'>,
) {
  const processInstanceId = normalizeText(message.templateParams?.processInstanceId);
  const taskId = normalizeText(message.templateParams?.taskId);
  const detailUrl = normalizeText(message.templateParams?.detailUrl);
  const urlSource =
    detailUrl ||
    (typeof message.templateParams?.url === 'string' ? message.templateParams.url : '');

  let idFromUrl = '';
  let taskIdFromUrl = '';
  if (urlSource) {
    try {
      const parsed = new URL(urlSource);
      idFromUrl = parsed.searchParams.get('id') || '';
      taskIdFromUrl = parsed.searchParams.get('taskId') || '';
    } catch {
      const rawQuery = urlSource.split('?')[1] || '';
      const params = new URLSearchParams(rawQuery);
      idFromUrl = params.get('id') || '';
      taskIdFromUrl = params.get('taskId') || '';
    }
  }

  const processId = processInstanceId || idFromUrl;
  const resolvedTaskId = taskId || taskIdFromUrl;
  if (!processId) {
    return undefined;
  }
  return {
    path: '/oa-lite/center',
    query: {
      view: 'center',
      detailSection: resolveWorkbenchDetailSection(message.templateCode),
      detailProcessInstanceId: processId,
      ...(resolvedTaskId ? { detailTaskId: resolvedTaskId } : {}),
      entry: 'approval',
    },
  } satisfies RouteLocationRaw;
}

function buildNoticeAction(
  message: Pick<SystemNotifyMessageApi.NotifyMessage, 'templateCode' | 'templateParams'>,
) {
  const route = resolveProcessDetailRoute(message);
  if (route) {
    return {
      label:
        message.templateCode === BPM_TASK_ASSIGNED_CODE ? '进入审批处理' : '查看流程详情',
      to: route,
    } satisfies NotificationAction;
  }
  const detailUrl = normalizeText(message.templateParams?.detailUrl);
  if (!detailUrl) {
    return undefined;
  }
  return {
    label: '查看流程详情',
    url: detailUrl,
  } satisfies NotificationAction;
}

function parseAssignedMessage(content: string) {
  const matched = content.match(/^您收到了一条新的待办任务：(.+?)-(.+?)，申请人：(.+)$/);
  if (!matched) {
    return undefined;
  }
  return {
    processName: matched[1]?.trim() || '',
    taskName: matched[2]?.trim() || '',
    startUserNickname: matched[3]?.trim() || '',
  };
}

function buildAssignedPresentation(
  message: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams'
  >,
): NotificationPresentation {
  const plain = stripHtmlContent(message.templateContent);
  const parsed = parseAssignedMessage(plain);
  const processName =
    normalizeText(message.templateParams?.processInstanceName) ||
    parsed?.processName ||
    '待审批流程';
  const taskName = normalizeText(message.templateParams?.taskName) || parsed?.taskName || '待审批';
  const startUserNickname =
    normalizeText(message.templateParams?.startUserNickname) ||
    parsed?.startUserNickname ||
    '相关发起人';

  return {
    action: buildNoticeAction(message),
    body: [
      '您有一条审批事项待处理，请及时查看并完成审批。',
      '该流程已流转至您，建议尽快核对流程内容、附件及审批意见后进行处理。',
    ],
    bodyTitle: '事项说明',
    fields: [
      { label: '流程名称', value: `《${processName}》` },
      { label: '当前节点', value: taskName },
      { label: '发起人', value: startUserNickname },
    ],
    preview: `待处理：${startUserNickname} 提交的《${processName}》，当前节点为“${taskName}”。`,
    statusLabel: '待处理',
    subtitle: '审批待处理通知',
    title: `请处理《${processName}》`,
    tone: 'warning',
  };
}

function buildApprovePresentation(
  message: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams'
  >,
): NotificationPresentation {
  const processName =
    normalizeText(message.templateParams?.processInstanceName) ||
    stripHtmlContent(message.templateContent).match(/流程【(.+?)】/)?.[1] ||
    '审批流程';
  return {
    action: buildNoticeAction(message),
    body: [
      '您发起的审批事项已审核通过，请知悉。',
      '如需回看完整审批记录、流转节点及处理意见，可点击下方按钮进入流程详情页查看。',
    ],
    bodyTitle: '事项说明',
    fields: [
      { label: '流程名称', value: `《${processName}》` },
      { label: '审批结果', value: '已通过' },
      { label: '通知类型', value: '流程结果通知' },
    ],
    preview: `审批通过：您发起的《${processName}》已完成审批。`,
    statusLabel: '已通过',
    subtitle: '审批结果通知',
    title: `《${processName}》已审批通过`,
    tone: 'success',
  };
}

function buildRejectPresentation(
  message: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams'
  >,
): NotificationPresentation {
  const processName =
    normalizeText(message.templateParams?.processInstanceName) ||
    stripHtmlContent(message.templateContent).match(/流程【(.+?)】/)?.[1] ||
    '审批流程';
  const reason =
    normalizeText(message.templateParams?.reason) ||
    stripHtmlContent(message.templateContent).match(/原因：(.+?)(，点击查看：|$)/)?.[1] ||
    '未填写审批意见';
  return {
    action: buildNoticeAction(message),
    body: [
      '您发起的审批事项未通过审核，请根据审批意见补充或修正后重新提交。',
      `审批意见：${reason}`,
    ],
    bodyTitle: '处理建议',
    fields: [
      { label: '流程名称', value: `《${processName}》` },
      { label: '审批结果', value: '已驳回' },
      { label: '驳回原因', value: reason },
    ],
    preview: `审批驳回：您发起的《${processName}》未通过，请查看处理意见。`,
    statusLabel: '已驳回',
    subtitle: '审批结果通知',
    title: `《${processName}》已被驳回`,
    tone: 'danger',
  };
}

function buildNoticePresentation(
  message: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams'
  >,
): NotificationPresentation {
  const plain = stripHtmlContent(message.templateContent);
  return {
    body: [plain || '请查看通知详情。'],
    bodyTitle: '通知内容',
    fields: [
      { label: '通知类型', value: '站内信通知' },
      { label: '消息来源', value: normalizeText(message.templateNickname) || '系统消息' },
    ],
    preview: plain || '点击查看详情',
    statusLabel: '已送达',
    subtitle: '通知消息',
    title: normalizeText(message.templateNickname) || '通知详情',
    tone: 'info',
  };
}

export function resolveNotificationPreview(
  item: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams'
  >,
) {
  const noticeId = extractNoticeId(item);
  if (noticeId) {
    const content =
      typeof item.templateParams?.content === 'string' ? item.templateParams.content : '';
    return stripHtmlContent(content || item.templateContent) || '点击查看公告详情';
  }
  return resolveNotificationPresentation(item).preview;
}

export function resolveNotificationPresentation(
  item: Pick<
    SystemNotifyMessageApi.NotifyMessage,
    'templateCode' | 'templateContent' | 'templateParams' | 'templateNickname'
  >,
): NotificationPresentation {
  const noticeId = extractNoticeId(item);
  if (noticeId) {
    return buildNoticePresentation(item);
  }
  switch (item.templateCode) {
    case BPM_TASK_ASSIGNED_CODE: {
      return buildAssignedPresentation(item);
    }
    case BPM_PROCESS_APPROVE_CODE: {
      return buildApprovePresentation(item);
    }
    case BPM_PROCESS_REJECT_CODE: {
      return buildRejectPresentation(item);
    }
    default: {
      return buildNoticePresentation(item);
    }
  }
}
