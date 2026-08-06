<script lang="ts" setup>
import type { BpmCategoryApi } from '#/api/bpm/category';
import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { BpmTaskApi } from '#/api/bpm/task';

import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { BpmModelFormType, BpmProcessInstanceStatus } from '@vben/constants';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';
import { useUserStore } from '@vben/stores';
import { formatDateTime, formatPast2 } from '@vben/utils';
import { useWebSocket } from '@vueuse/core';

import {
  Button,
  ConfigProvider,
  DatePicker,
  Empty,
  Input,
  message,
  Pagination,
  Select,
  Spin,
  Tag,
  theme as antdTheme,
} from 'ant-design-vue';

import { getCategorySimpleList } from '#/api/bpm/category';
import { getApprovalTemplateList } from '#/api/bpm/approvalTemplate';
import {
  getProcessDefinition,
} from '#/api/bpm/definition';
import {
  getProcessInstanceCopyPage,
  getProcessInstanceManagerPage,
  getProcessInstanceMyPage,
} from '#/api/bpm/processInstance';
import { getTaskDonePage, getTaskTodoPage } from '#/api/bpm/task';
import { router } from '#/router';
import {
  buildKodEntryQuery,
  isApprovalEntryQuery,
  isForceCreateEntry,
  KOD_ENTRY_APPROVAL,
} from '#/utils/kod-entry';
import { normalizeOaAssetUrl } from '#/utils';
import { isAdminUser } from '#/utils/oa-user';
import ProcessDetail, {
  type OaLiteDetailRequest,
  type OaLiteDetailSection,
} from './components/process-detail.vue';

defineOptions({ name: 'OALiteHome' });

type MainTab =
  | 'all-process'
  | 'create'
  | 'copied'
  | 'initiated'
  | 'pending'
  | 'processed';
type ListTab = Exclude<MainTab, 'create'>;
type DateRangeValue = [string, string];
type DetailPayload =
  | BpmTaskApi.Task
  | BpmProcessInstanceApi.ProcessInstance
  | BpmProcessInstanceApi.ProcessInstanceCopyRespVO
  | null;

interface OaTaskAssignedWebSocketMessage {
  assigneeUserId: number;
  processInstanceId: string;
  processInstanceName: string;
  startUserId: number;
  startUserNickname: string;
  taskId: string;
  taskName: string;
}

interface ListFilterState {
  category?: string;
  createTime?: DateRangeValue;
  name: string;
  processDefinitionId?: string;
  processDefinitionKey?: string;
  status?: number;
}

interface ListPageState {
  pageNo: number;
  pageSize: number;
  total: number;
}

interface OaTemplateCard {
  description: string;
  definition: BpmProcessDefinitionApi.ProcessDefinition;
  icon: string;
  key: string;
  title: string;
}

interface SelectOption {
  label: string;
  value: number | string;
}

const DEFAULT_PAGE_SIZE = 10;
const OA_LITE_CREATE_PATH = '/oa-lite';
const OA_LITE_CENTER_PATH = '/oa-lite/center';
const OA_LITE_TASK_ASSIGNED_MESSAGE_TYPE = 'task-assigned';
const OA_LITE_TASK_ASSIGNED_TOAST_KEY = 'oa-lite-task-assigned';
const accessStore = useAccessStore();
const userStore = useUserStore();
const route = useRoute();

const initializing = ref(true);
const activeTab = ref<MainTab>('create');
const lastCenterTab = ref<ListTab>('pending');
const selectedCreateCategoryCode = ref<string>();
const selectedItem = ref<DetailPayload>(null);
const categories = ref<BpmCategoryApi.Category[]>([]);
const oaTemplateDefinitions = ref<BpmProcessDefinitionApi.ProcessDefinition[]>([]);
const todoItems = ref<BpmTaskApi.Task[]>([]);
const doneItems = ref<BpmTaskApi.Task[]>([]);
const initiatedItems = ref<BpmProcessInstanceApi.ProcessInstance[]>([]);
const managerProcessItems = ref<BpmProcessInstanceApi.ProcessInstance[]>([]);
const copiedItems = ref<BpmProcessInstanceApi.ProcessInstanceCopyRespVO[]>([]);
const createCategorySectionElements = ref<Record<string, HTMLElement | null>>({});
const isCurrentUserAdmin = computed(() => isAdminUser(userStore.userRoles));
const listTabs = computed<ListTab[]>(() =>
  isCurrentUserAdmin.value
    ? ['pending', 'processed', 'initiated', 'all-process', 'copied']
    : ['pending', 'processed', 'initiated', 'copied'],
);

const tabLoading = reactive<Record<ListTab, boolean>>({
  'all-process': false,
  copied: false,
  initiated: false,
  pending: false,
  processed: false,
});
const tabInitialized = reactive<Record<ListTab, boolean>>({
  'all-process': false,
  copied: false,
  initiated: false,
  pending: false,
  processed: false,
});
const tabPages = reactive<Record<ListTab, ListPageState>>({
  'all-process': { pageNo: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 },
  copied: { pageNo: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 },
  initiated: { pageNo: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 },
  pending: { pageNo: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 },
  processed: { pageNo: 1, pageSize: DEFAULT_PAGE_SIZE, total: 0 },
});

function createDefaultFilter(): ListFilterState {
  return {
    category: undefined,
    createTime: undefined,
    name: '',
    processDefinitionId: undefined,
    processDefinitionKey: undefined,
    status: undefined,
  };
}

const listFilters = reactive<Record<ListTab, ListFilterState>>({
  'all-process': createDefaultFilter(),
  copied: createDefaultFilter(),
  initiated: createDefaultFilter(),
  pending: createDefaultFilter(),
  processed: createDefaultFilter(),
});

const processStatusOptions: SelectOption[] = [
  { label: '进行中', value: BpmProcessInstanceStatus.RUNNING },
  { label: '已通过', value: BpmProcessInstanceStatus.APPROVE },
  { label: '已驳回', value: BpmProcessInstanceStatus.REJECT },
  { label: '已取消', value: BpmProcessInstanceStatus.CANCEL },
];
const taskStatusOptions: SelectOption[] = [
  { label: '进行中', value: 1 },
  { label: '已通过', value: 2 },
  { label: '已驳回', value: 3 },
  { label: '已取消', value: 4 },
];

const oaLiteTheme = {
  algorithm: [antdTheme.defaultAlgorithm],
  token: {
    colorBgBase: '#ffffff',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#d7dee8',
    colorBorderSecondary: '#e6ebf2',
    colorFillSecondary: '#f3f6fa',
    colorFillTertiary: '#eef2f7',
    colorPrimary: '#1565c0',
    colorPrimaryActive: '#0b57a1',
    colorPrimaryHover: '#0b57a1',
    colorSplit: '#e6ebf2',
    colorText: '#17202d',
    colorTextQuaternary: '#7d8a9b',
    colorTextSecondary: '#4c5b70',
    colorTextTertiary: '#6a788d',
  },
};
const selectApproverLabel = JSON.stringify('选择审批人');

const webSocketServer = ref('');
const {
  data: webSocketData,
  close: closeWebSocket,
  open: openWebSocket,
} = useWebSocket(webSocketServer, {
  autoReconnect: true,
  heartbeat: true,
  immediate: false,
});

function buildWebSocketServer(refreshToken: string) {
  return `${`${import.meta.env.VITE_BASE_URL}/infra/ws`.replace(
    'http',
    'ws',
  )}?token=${encodeURIComponent(refreshToken)}`;
}

function connectTaskWebSocket() {
  const refreshToken = accessStore.refreshToken as string;
  if (!refreshToken) {
    return;
  }
  const nextServer = buildWebSocketServer(refreshToken);
  if (webSocketServer.value !== nextServer) {
    closeWebSocket();
    webSocketServer.value = nextServer;
  }
  openWebSocket();
}

function resolveTenantIdFromQuery() {
  const tenantId = route.query.tenantId;
  const tenantIdText = Array.isArray(tenantId) ? tenantId[0] : tenantId;
  if (!tenantIdText) {
    return null;
  }
  const parsedTenantId = Number(tenantIdText);
  return Number.isFinite(parsedTenantId) && parsedTenantId > 0
    ? parsedTenantId
    : null;
}

async function handleKodSsoEntryRedirect() {
  const tenantId = resolveTenantIdFromQuery();
  if (tenantId) {
    accessStore.setTenantId(tenantId);
  }

  const kodSsoCode = route.query.kodSsoCode;
  const code = Array.isArray(kodSsoCode) ? kodSsoCode[0] : kodSsoCode;
  if (!code) {
    return false;
  }
  if (accessStore.accessToken) {
    await clearKodSsoCodeFromQuery();
    return false;
  }
  await router.replace({
    path: '/auth/kod-sso-login',
    query: { ...route.query },
  });
  return true;
}

async function clearKodSsoCodeFromQuery() {
  if (!('kodSsoCode' in route.query)) {
    return;
  }
  const nextQuery = { ...route.query };
  delete nextQuery.kodSsoCode;
  await router.replace({
    path: route.path,
    query: nextQuery,
  });
}

function buildApprovalEntryQuery() {
  return isApprovalEntryQuery(route.query)
    ? buildKodEntryQuery(KOD_ENTRY_APPROVAL, route.query)
    : route.query;
}

function shouldForceCreateMode() {
  return route.path === OA_LITE_CREATE_PATH && isForceCreateEntry(route.query);
}

function isImageIcon(icon?: string) {
  if (!icon) {
    return false;
  }
  return /^(https?:\/\/|\/|data:)/.test(icon);
}

const availableTemplateDefinitions = computed<OaTemplateCard[]>(() => {
  return oaTemplateDefinitions.value
    .map((definition) => ({
      definition,
      description: definition.description || `${definition.name}审批流程`,
      icon:
        normalizeOaAssetUrl(definition.icon) || 'solar:document-text-outline',
      key: definition.id,
      title: definition.name,
    }))
    .sort((left, right) => {
      const leftSort = Number(left.definition.sort ?? 0);
      const rightSort = Number(right.definition.sort ?? 0);
      if (leftSort !== rightSort) {
        return leftSort - rightSort;
      }
      return Number(right.definition.deploymentTime || 0) - Number(left.definition.deploymentTime || 0);
    });
});

const createCategoryTabs = computed<BpmCategoryApi.Category[]>(() => {
  const categoryMap = new Map<string, BpmCategoryApi.Category>();
  availableTemplateDefinitions.value.forEach((item, index) => {
    const definition = item.definition;
    categoryMap.set(definition.category, {
      code: definition.category,
      description: undefined,
      id: index + 1,
      name:
        definition.categoryName ||
        categories.value.find((category) => category.code === definition.category)?.name ||
        '未分类',
      sort: index,
      status: 0,
    });
  });
  return [...categoryMap.values()];
});

const createCategorySections = computed(() =>
  createCategoryTabs.value.map((category) => ({
    ...category,
    templates: availableTemplateDefinitions.value.filter(
      (item) => item.definition.category === category.code,
    ),
  })),
);

const stats = computed(() => ({
  allProcess: tabPages['all-process'].total,
  copied: tabPages.copied.total,
  initiated: tabPages.initiated.total,
  pending: tabPages.pending.total,
  processed: tabPages.processed.total,
}));

const dashboardNavItems = computed(() => {
  const items: {
    count: number;
    icon: string;
    key: ListTab;
    label: string;
  }[] = [
    {
      count: stats.value.pending,
      icon: 'solar:checklist-minimalistic-outline',
      key: 'pending',
      label: '待我审批',
    },
    {
      count: stats.value.processed,
      icon: 'solar:verified-check-outline',
      key: 'processed',
      label: '我已审批',
    },
    {
      count: stats.value.initiated,
      icon: 'solar:clipboard-text-outline',
      key: 'initiated',
      label: '我发起的',
    },
  ];
  if (isCurrentUserAdmin.value) {
    items.push({
      count: stats.value.allProcess,
      icon: 'solar:documents-minimalistic-outline',
      key: 'all-process',
      label: '全部流程',
    });
  }
  items.push({
    count: stats.value.copied,
    icon: 'solar:inbox-line-outline',
    key: 'copied',
    label: '抄送我的',
  });
  return items;
});

const categoryOptions = computed<SelectOption[]>(() =>
  categories.value.map((item) => ({
    label: item.name,
    value: item.code,
  })),
);
const processTemplateIdOptions = computed<SelectOption[]>(() =>
  availableTemplateDefinitions.value.map((item) => ({
    label: item.definition.name,
    value: item.definition.id,
  })),
);
const processTemplateKeyOptions = computed<SelectOption[]>(() =>
  availableTemplateDefinitions.value.map((item) => ({
    label: item.definition.name,
    value: item.definition.key || item.definition.id,
  })),
);
const currentStatusOptions = computed<SelectOption[]>(() =>
  activeTab.value === 'processed' ? taskStatusOptions : processStatusOptions,
);
const currentProcessOptions = computed<SelectOption[]>(() =>
  activeTab.value === 'copied'
    ? processTemplateIdOptions.value
    : processTemplateKeyOptions.value,
);
const currentProcessFilterValue = computed<string | undefined>({
  get() {
    if (activeTab.value === 'create') {
      return undefined;
    }
    return activeTab.value === 'copied'
      ? listFilters.copied.processDefinitionId
      : listFilters[activeTab.value].processDefinitionKey;
  },
  set(value) {
    if (activeTab.value === 'create') {
      return;
    }
    if (activeTab.value === 'copied') {
      listFilters.copied.processDefinitionId = value;
      return;
    }
    listFilters[activeTab.value].processDefinitionKey = value;
  },
});

const currentFilter = computed(() =>
  activeTab.value === 'create' ? null : listFilters[activeTab.value],
);
const currentPageState = computed(() =>
  activeTab.value === 'create' ? null : tabPages[activeTab.value],
);
const currentListLoading = computed(() =>
  activeTab.value === 'create' ? false : tabLoading[activeTab.value],
);
const currentList = computed(() => {
  if (activeTab.value === 'create') {
    return [];
  }
  return getListSource(activeTab.value);
});
const currentDetailSection = computed<OaLiteDetailSection>(() => {
  switch (activeTab.value) {
    case 'all-process':
      return 'initiated';
    case 'copied':
      return 'copied';
    case 'pending':
      return 'pending';
    case 'processed':
      return 'processed';
    default:
      return 'initiated';
  }
});
const currentDetailRequest = computed<null | OaLiteDetailRequest>(() => {
  if (!selectedItem.value) {
    return null;
  }
  if (isTaskItem(selectedItem.value)) {
    return {
      businessKey: selectedItem.value.processInstance?.businessKey,
      processInstanceId: String(
        selectedItem.value.processInstance?.id || selectedItem.value.processInstanceId,
      ),
      taskId: selectedItem.value.id,
    };
  }
  if (isCopiedItem(selectedItem.value)) {
    return {
      activityId: selectedItem.value.activityId || undefined,
      processInstanceId: String(selectedItem.value.processInstanceId),
      taskId: selectedItem.value.taskId || undefined,
    };
  }
  return {
    businessKey: selectedItem.value.businessKey,
    processInstanceId: String(selectedItem.value.id),
  };
});
const isCenterMode = computed(() => activeTab.value !== 'create');

const currentListTitle = computed(() => {
  switch (activeTab.value) {
    case 'all-process':
      return '全部流程';
    case 'pending':
      return '待我审批';
    case 'processed':
      return '我已审批';
    case 'initiated':
      return '我发起的';
    case 'copied':
      return '抄送我的';
    default:
      return '审批中心';
  }
});
const showProcessFilter = computed(
  () =>
    activeTab.value === 'all-process' ||
    activeTab.value === 'initiated' ||
    activeTab.value === 'pending' ||
    activeTab.value === 'processed',
);
const showCategoryFilter = computed(
  () =>
    activeTab.value === 'all-process' ||
    activeTab.value === 'initiated' ||
    activeTab.value === 'pending' ||
    activeTab.value === 'processed',
);
const showStatusFilter = computed(
  () =>
    activeTab.value === 'all-process' ||
    activeTab.value === 'initiated' ||
    activeTab.value === 'processed',
);

function isTaskItem(item: DetailPayload): item is BpmTaskApi.Task {
  return Boolean(item && 'processInstance' in item);
}

function isCopiedItem(
  item: DetailPayload,
): item is BpmProcessInstanceApi.ProcessInstanceCopyRespVO {
  return Boolean(item && 'processInstanceId' in item && 'activityName' in item);
}

function getListSource(tab: ListTab) {
  switch (tab) {
    case 'all-process':
      return managerProcessItems.value;
    case 'copied':
      return copiedItems.value;
    case 'initiated':
      return initiatedItems.value;
    case 'pending':
      return todoItems.value;
    case 'processed':
      return doneItems.value;
  }
}

function getItemIdentity(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isCopiedItem(item)) {
    return `copy-${item.id}-${item.processInstanceId}-${item.activityId}`;
  }
  if (isTaskItem(item)) {
    return `task-${item.id}`;
  }
  return `process-${item.id}`;
}

function syncSelectedItem(tab: ListTab) {
  const list = getListSource(tab);
  const currentIdentity = getItemIdentity(selectedItem.value);
  const matchedItem = currentIdentity
    ? list.find((item) => getItemIdentity(item) === currentIdentity)
    : undefined;
  selectedItem.value = matchedItem || list[0] || null;
}

function getSummaryText(summary?: { key: string; value: string }[]) {
  if (!summary?.length) {
    return '';
  }
  return summary.map((item) => `${item.key}：${item.value}`).join(' / ');
}

function getProcessStatusText(status?: number) {
  switch (status) {
    case BpmProcessInstanceStatus.APPROVE:
      return '已通过';
    case BpmProcessInstanceStatus.CANCEL:
      return '已取消';
    case BpmProcessInstanceStatus.REJECT:
      return '已驳回';
    case BpmProcessInstanceStatus.RUNNING:
      return '进行中';
    default:
      return '处理中';
  }
}

function dedupeDoneTasks(tasks: BpmTaskApi.Task[]) {
  const taskMap = new Map<string, BpmTaskApi.Task>();
  tasks.forEach((task) => {
    const processInstanceId = String(
      task.processInstanceId || task.processInstance?.id || '',
    );
    if (!processInstanceId) {
      taskMap.set(`task-${task.id}`, task);
      return;
    }
    const current = taskMap.get(processInstanceId);
    if (!current) {
      taskMap.set(processInstanceId, task);
      return;
    }
    const currentTime = new Date(current.endTime || current.createTime || 0).getTime();
    const nextTime = new Date(task.endTime || task.createTime || 0).getTime();
    if (nextTime >= currentTime) {
      taskMap.set(processInstanceId, task);
    }
  });
  return [...taskMap.values()];
}

function getItemStatus(item: DetailPayload) {
  if (!item) {
    return undefined;
  }
  if (isTaskItem(item)) {
    return item.processInstance?.status ?? item.status;
  }
  if (isCopiedItem(item)) {
    return undefined;
  }
  return item.status;
}

function getItemStatusText(item: DetailPayload) {
  const status = getItemStatus(item);
  return status === undefined ? '' : getProcessStatusText(status);
}

function getItemStatusTone(item: DetailPayload) {
  const status = getItemStatus(item);
  switch (status) {
    case BpmProcessInstanceStatus.APPROVE:
      return 'success';
    case BpmProcessInstanceStatus.REJECT:
      return 'danger';
    case BpmProcessInstanceStatus.CANCEL:
      return 'muted';
    case BpmProcessInstanceStatus.RUNNING:
      return 'warning';
    default:
      return 'neutral';
  }
}

function getItemTitle(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isTaskItem(item)) {
    return item.processInstance?.name || '';
  }
  if (isCopiedItem(item)) {
    return item.processInstanceName || '';
  }
  return item.name || '';
}

function getItemSummary(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isTaskItem(item)) {
    return getSummaryText(item.processInstance?.summary as { key: string; value: string }[] | undefined);
  }
  if (isCopiedItem(item)) {
    return getSummaryText(item.summary);
  }
  return getSummaryText(item.summary);
}

function getItemMetaLeft(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isTaskItem(item)) {
    return `当前节点：${item.name}`;
  }
  if (isCopiedItem(item)) {
    return `抄送节点：${item.activityName || '-'}`;
  }
  if (
    item.status === BpmProcessInstanceStatus.RUNNING &&
    item.tasks &&
    item.tasks.length > 0
  ) {
    const firstTask = item.tasks[0];
    if (!firstTask) {
      return getProcessStatusText(item.status);
    }
    if (item.tasks.length === 1) {
      return `${firstTask.assigneeUser?.nickname || '审批人'}（${firstTask.name}）进行中`;
    }
    return `${firstTask.assigneeUser?.nickname || '审批人'} 等 ${item.tasks.length} 人（${firstTask.name}）进行中`;
  }
  return getProcessStatusText(item.status);
}

function getItemMetaRight(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isTaskItem(item)) {
    return activeTab.value === 'processed'
      ? `处理时间：${formatDateTime(item.endTime || item.createTime)}`
      : `任务时间：${formatDateTime(item.createTime)}`;
  }
  if (isCopiedItem(item)) {
    return `抄送时间：${formatDateTime(item.createTime)}`;
  }
  return activeTab.value === 'initiated'
    ? `发起时间：${formatDateTime(item.startTime || item.createTime)}`
    : `结束时间：${formatDateTime(item.endTime || item.createTime)}`;
}

function getCompactMetaText(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isCopiedItem(item)) {
    return [
      `发起人：${item.startUser?.nickname || '-'}`,
      `抄送人：${item.createUser?.nickname || '-'}`,
    ].join(' / ');
  }
  if (isTaskItem(item)) {
    if (activeTab.value === 'processed') {
      return [
        `发起人：${item.processInstance?.startUser?.nickname || '-'}`,
        item.durationInMillis ? `耗时：${formatPast2(item.durationInMillis)}` : '',
      ]
        .filter(Boolean)
        .join(' / ');
    }
    return `发起人：${item.processInstance?.startUser?.nickname || '-'}`;
  }
  return [
    `流程分类：${item.categoryName || item.category || '-'}`,
    item.businessKey ? `业务编号：${item.businessKey}` : '',
  ]
    .filter(Boolean)
    .join(' / ');
}

function getListSecondaryText(item: DetailPayload) {
  return getItemSummary(item) || getCompactMetaText(item);
}

function getKeywordPlaceholder() {
  switch (activeTab.value) {
    case 'all-process':
      return '请输入流程名称';
    case 'pending':
    case 'processed':
      return '请输入任务名称';
    case 'copied':
    case 'initiated':
      return '请输入流程名称';
    default:
      return '请输入关键字';
  }
}

function getCreateTimePlaceholder(): [string, string] {
  return activeTab.value === 'copied'
    ? ['开始抄送时间', '结束抄送时间']
    : ['开始发起时间', '结束发起时间'];
}

function getTabErrorMessage(tab: ListTab) {
  switch (tab) {
    case 'all-process':
      return '加载全部流程失败';
    case 'copied':
      return '加载抄送列表失败';
    case 'initiated':
      return '加载发起列表失败';
    case 'pending':
      return '加载待办列表失败';
    case 'processed':
      return '加载已办列表失败';
  }
}

async function loadBaseOptions() {
  categories.value = await getCategorySimpleList().catch(() => []);
}

async function loadProcessDefinitions() {
  const definitionList = await getApprovalTemplateList().catch(() => []);
  oaTemplateDefinitions.value = (definitionList || []).filter(
    (item) => item.id && item.name,
  );
}

async function loadTabData(tab: ListTab) {
  tabLoading[tab] = true;
  try {
    const pageState = tabPages[tab];
    const filter = listFilters[tab];
    const createTime = filter.createTime ? [...filter.createTime] : undefined;

    switch (tab) {
      case 'all-process': {
        const resp = await getProcessInstanceManagerPage({
          pageNo: pageState.pageNo,
          pageSize: pageState.pageSize,
          name: filter.name.trim() || undefined,
          category: filter.category,
          processDefinitionKey: filter.processDefinitionKey,
          status: filter.status,
          createTime,
        });
        managerProcessItems.value = resp.list || [];
        pageState.total = resp.total || 0;
        break;
      }
      case 'initiated': {
        const resp = await getProcessInstanceMyPage({
          pageNo: pageState.pageNo,
          pageSize: pageState.pageSize,
          name: filter.name.trim() || undefined,
          category: filter.category,
          processDefinitionKey: filter.processDefinitionKey,
          status: filter.status,
          createTime,
        });
        initiatedItems.value = resp.list || [];
        pageState.total = resp.total || 0;
        break;
      }
      case 'pending': {
        const resp = await getTaskTodoPage({
          pageNo: pageState.pageNo,
          pageSize: pageState.pageSize,
          name: filter.name.trim() || undefined,
          category: filter.category,
          processDefinitionKey: filter.processDefinitionKey,
          createTime,
        });
        todoItems.value = resp.list || [];
        pageState.total = resp.total || 0;
        break;
      }
      case 'processed': {
        const resp = await getTaskDonePage({
          pageNo: pageState.pageNo,
          pageSize: pageState.pageSize,
          name: filter.name.trim() || undefined,
          category: filter.category,
          processDefinitionKey: filter.processDefinitionKey,
          status: filter.status,
          createTime,
        });
        doneItems.value = dedupeDoneTasks(resp.list || []);
        pageState.total = doneItems.value.length;
        break;
      }
      case 'copied': {
        const resp = await getProcessInstanceCopyPage({
          pageNo: pageState.pageNo,
          pageSize: pageState.pageSize,
          processInstanceName: filter.name.trim() || undefined,
          processDefinitionId: filter.processDefinitionId,
          createTime,
        });
        copiedItems.value = resp.list || [];
        pageState.total = resp.total || 0;
        break;
      }
    }
    tabInitialized[tab] = true;
    if (activeTab.value === tab) {
      syncSelectedItem(tab);
    }
  } catch (error: any) {
    message.error(error?.message || getTabErrorMessage(tab));
  } finally {
    tabLoading[tab] = false;
  }
}

async function refreshAllTabs() {
  await Promise.all(listTabs.value.map((tab) => loadTabData(tab)));
}

async function ensureDefinitionDetail(
  definition: BpmProcessDefinitionApi.ProcessDefinition,
) {
  if (
    definition.formType !== BpmModelFormType.NORMAL ||
    definition.formConf ||
    definition.formFields?.length
  ) {
    return definition;
  }
  return await getProcessDefinition(definition.id, definition.key);
}

async function openTemplateCreate(
  definition: BpmProcessDefinitionApi.ProcessDefinition,
  businessKey?: string,
) {
  const definitionDetail = await ensureDefinitionDetail(definition);
  if (definitionDetail.formType === BpmModelFormType.NORMAL) {
    await router.push({
      name: 'BpmProcessInstanceCreate',
      query: {
        processDefinitionId: definitionDetail.id,
        returnTo: 'oa-lite',
        ...(isApprovalEntryQuery(route.query)
          ? { entry: KOD_ENTRY_APPROVAL }
          : {}),
      },
    });
    return;
  }
  if (definitionDetail.formCustomCreatePath) {
    await router.push({
      path: definitionDetail.formCustomCreatePath,
      query: {
        ...(businessKey ? { id: businessKey } : {}),
        returnTo: 'oa-lite',
        ...(isApprovalEntryQuery(route.query)
          ? { entry: KOD_ENTRY_APPROVAL }
          : {}),
      },
    });
    return;
  }
  message.warning('当前流程尚未配置发起入口');
}

function handleProcessRecreate(
  processInstanceId: string,
  businessKey?: string,
  processDefinitionKey?: string,
  formCustomCreatePath?: string,
) {
  const targetDefinition = oaTemplateDefinitions.value.find(
    (item) => item.key === processDefinitionKey,
  );
  if (formCustomCreatePath) {
    router.push({
      path: formCustomCreatePath,
      query: {
        ...(businessKey ? { id: businessKey } : {}),
        returnTo: 'oa-lite',
        ...(isApprovalEntryQuery(route.query)
          ? { entry: KOD_ENTRY_APPROVAL }
          : {}),
      },
    });
    return;
  }
  if (targetDefinition?.formType === BpmModelFormType.NORMAL) {
    router.push({
      name: 'BpmProcessInstanceCreate',
      query: {
        processDefinitionId: targetDefinition.id,
        processInstanceId,
        returnTo: 'oa-lite',
        ...(isApprovalEntryQuery(route.query)
          ? { entry: KOD_ENTRY_APPROVAL }
          : {}),
      },
    });
    return;
  }
  message.warning('当前流程尚未配置重新发起入口');
}

function setCreateCategorySectionRef(code: string, element: HTMLElement | null) {
  if (!element) {
    delete createCategorySectionElements.value[code];
    return;
  }
  createCategorySectionElements.value[code] = element;
}

function selectCreateCategory(code: string) {
  selectedCreateCategoryCode.value = code;
  const target = createCategorySectionElements.value[code];
  if (!target || typeof window === 'undefined') {
    return;
  }
  const top = target.getBoundingClientRect().top + window.scrollY - 132;
  window.scrollTo({
    behavior: 'smooth',
    top: Math.max(top, 0),
  });
}

async function openTab(tab: MainTab) {
  if (tab !== 'create') {
    lastCenterTab.value = tab;
  }
  activeTab.value = tab;
  const targetPath = tab === 'create' ? OA_LITE_CREATE_PATH : OA_LITE_CENTER_PATH;
  if (route.path !== targetPath) {
    await router.replace({
      path: targetPath,
      query: buildApprovalEntryQuery(),
    });
  }
}

async function handleFilterSubmit() {
  if (activeTab.value === 'create') {
    return;
  }
  tabPages[activeTab.value].pageNo = 1;
  await loadTabData(activeTab.value);
}

async function resetCurrentFilter() {
  if (activeTab.value === 'create') {
    return;
  }
  Object.assign(listFilters[activeTab.value], createDefaultFilter());
  tabPages[activeTab.value].pageNo = 1;
  await loadTabData(activeTab.value);
}

async function handlePageChange(page: number, pageSize: number) {
  if (activeTab.value === 'create') {
    return;
  }
  const pageState = tabPages[activeTab.value];
  pageState.pageNo = page;
  pageState.pageSize = pageSize;
  await loadTabData(activeTab.value);
}

async function handleDetailRefresh() {
  await refreshAllTabs();
  if (activeTab.value !== 'create') {
    syncSelectedItem(activeTab.value);
  }
}

function parseTaskAssignedWebSocketMessage(
  rawMessage: string,
): null | OaTaskAssignedWebSocketMessage {
  if (rawMessage === 'pong') {
    return null;
  }
  const envelope = JSON.parse(rawMessage);
  if (envelope.type !== OA_LITE_TASK_ASSIGNED_MESSAGE_TYPE || !envelope.content) {
    return null;
  }
  return JSON.parse(envelope.content) as OaTaskAssignedWebSocketMessage;
}

async function openPendingTaskDetail(taskId: string) {
  activeTab.value = 'pending';
  lastCenterTab.value = 'pending';
  if (route.path !== OA_LITE_CENTER_PATH) {
    await router.replace({
      path: OA_LITE_CENTER_PATH,
      query: buildApprovalEntryQuery(),
    });
  }
  if (!tabInitialized.pending) {
    await loadTabData('pending');
  }
  const matchedTask = todoItems.value.find((item) => String(item.id) === String(taskId));
  if (matchedTask) {
    selectedItem.value = matchedTask;
    return;
  }
  await loadTabData('pending');
  selectedItem.value =
    todoItems.value.find((item) => String(item.id) === String(taskId)) || todoItems.value[0] || null;
}

async function handleTaskAssignedWebSocketMessage(
  messagePayload: OaTaskAssignedWebSocketMessage,
) {
  await loadTabData('pending');
  if (activeTab.value === 'pending') {
    syncSelectedItem('pending');
  }
  message.open({
    content: `${messagePayload.startUserNickname} 提交了新的审批待办：${messagePayload.taskName}`,
    duration: 4,
    key: OA_LITE_TASK_ASSIGNED_TOAST_KEY,
    onClick: () => {
      openPendingTaskDetail(messagePayload.taskId);
    },
    type: 'info',
  });
}

watch(
  createCategoryTabs,
  (tabs) => {
    const firstTab = tabs[0];
    if (!firstTab) {
      selectedCreateCategoryCode.value = undefined;
      return;
    }
    if (
      selectedCreateCategoryCode.value &&
      tabs.some((item) => item.code === selectedCreateCategoryCode.value)
    ) {
      return;
    }
    selectedCreateCategoryCode.value = firstTab.code;
  },
  { immediate: true },
);

watch(
  () => isCurrentUserAdmin.value,
  (isAdmin) => {
    if (isAdmin) {
      return;
    }
    tabInitialized['all-process'] = false;
    tabPages['all-process'].pageNo = 1;
    tabPages['all-process'].total = 0;
    managerProcessItems.value = [];
    if (activeTab.value === 'all-process') {
      activeTab.value = 'pending';
      lastCenterTab.value = 'pending';
    }
  },
  { immediate: true },
);

watch(
  () => route.path,
  (path) => {
    if (shouldForceCreateMode()) {
      activeTab.value = 'create';
      return;
    }
    if (path === OA_LITE_CREATE_PATH) {
      activeTab.value = 'create';
      return;
    }
    if (path === OA_LITE_CENTER_PATH && activeTab.value === 'create') {
      activeTab.value = lastCenterTab.value;
    }
  },
  { immediate: true },
);

watch(
  () => activeTab.value,
  async (tab) => {
    if (shouldForceCreateMode() && tab !== 'create') {
      activeTab.value = 'create';
      return;
    }
    if (tab === 'create') {
      selectedItem.value = null;
      return;
    }
    if (tab === 'all-process' && !isCurrentUserAdmin.value) {
      activeTab.value = 'pending';
      lastCenterTab.value = 'pending';
      return;
    }
    lastCenterTab.value = tab;
    if (!tabInitialized[tab]) {
      await loadTabData(tab);
      return;
    }
    syncSelectedItem(tab);
  },
);

watch(
  () => webSocketData.value,
  async (rawMessage) => {
    if (!rawMessage) {
      return;
    }
    try {
      const messagePayload = parseTaskAssignedWebSocketMessage(rawMessage);
      if (!messagePayload) {
        return;
      }
      await handleTaskAssignedWebSocketMessage(messagePayload);
    } catch (error) {
      console.error('处理 OA 实时待办消息失败', error);
    }
  },
);

onMounted(async () => {
  try {
    const redirectedToKodSsoLogin = await handleKodSsoEntryRedirect();
    if (redirectedToKodSsoLogin) {
      return;
    }
    connectTaskWebSocket();
    await Promise.all([loadBaseOptions(), loadProcessDefinitions(), refreshAllTabs()]);
    if (availableTemplateDefinitions.value.length === 0) {
      message.warning('当前账号暂无可发起的流程');
    }
  } catch (error: any) {
    message.error(error?.message || '加载 OA 工作台失败');
  } finally {
    initializing.value = false;
  }
});

onUnmounted(() => {
  closeWebSocket();
});
</script>

<template>
  <ConfigProvider :theme="oaLiteTheme">
    <div class="oa-lite-page">
      <div class="oa-lite-bg"></div>

      <main
        class="oa-lite-main oa-lite-main-embedded"
        :class="{ 'is-center-mode': isCenterMode }"
      >
        <Spin :spinning="initializing">
          <div class="oa-lite-home-shell" :class="{ 'is-center-mode': isCenterMode }">
            <template v-if="activeTab === 'create'">
              <section class="oa-lite-section-header">
                <div>
                  <div class="oa-lite-section-title">发起审批</div>
                </div>
              </section>

              <section class="oa-lite-stat-pillar">
                <button
                  v-for="item in dashboardNavItems"
                  :key="item.key"
                  class="oa-lite-stat-item"
                  @click="openTab(item.key)"
                >
                  <span class="oa-lite-stat-count">{{ item.count }}</span>
                  <IconifyIcon :icon="item.icon" class="oa-lite-stat-icon" />
                  <span class="oa-lite-stat-label">{{ item.label }}</span>
                  <IconifyIcon
                    icon="solar:alt-arrow-right-outline"
                    class="oa-lite-stat-arrow"
                  />
                </button>
              </section>

              <section class="oa-lite-create-shell">
                <div v-if="createCategoryTabs.length > 0" class="oa-lite-create-toolbar">
                  <div class="oa-lite-category-tabs">
                      <button
                        v-for="item in createCategoryTabs"
                        :key="item.code"
                        class="oa-lite-category-tab"
                        :class="{ active: selectedCreateCategoryCode === item.code }"
                        @click="selectCreateCategory(item.code)"
                      >
                        {{ item.name }}
                      </button>
                  </div>
                </div>

                <div v-if="createCategorySections.length > 0" class="oa-lite-create-sections">
                  <section
                    v-for="section in createCategorySections"
                    :key="section.code"
                    :ref="
                      (element) =>
                        setCreateCategorySectionRef(
                          section.code,
                          element as HTMLElement | null,
                        )
                    "
                    class="oa-lite-template-section"
                  >
                    <div class="oa-lite-template-section-head">
                      <span class="oa-lite-template-section-title">{{ section.name }}</span>
                      <IconifyIcon
                        icon="solar:alt-arrow-right-line-duotone"
                        class="oa-lite-template-section-arrow"
                      />
                    </div>

                    <div class="oa-lite-template-grid">
                      <button
                        v-for="item in section.templates"
                        :key="item.key"
                        class="oa-lite-template-card"
                        @click="openTemplateCreate(item.definition)"
                      >
                        <div class="oa-lite-template-icon">
                          <img
                            v-if="isImageIcon(item.icon)"
                            :src="item.icon"
                            alt=""
                            style="height: 24px; width: 24px; object-fit: contain"
                          />
                          <IconifyIcon v-else :icon="item.icon" />
                        </div>
                        <div class="oa-lite-template-body">
                          <div class="oa-lite-template-name">{{ item.title }}</div>
                          <div class="oa-lite-template-desc">
                            {{ item.description }}
                          </div>
                        </div>
                      </button>
                    </div>
                  </section>
                </div>

                <Empty
                  v-else
                  description="当前账号暂无可发起流程"
                  :image-style="{ height: '80px' }"
                />
              </section>
            </template>

            <template v-else>
              <section class="oa-lite-center-shell">
                <aside class="oa-lite-center-nav">
                  <div class="oa-lite-center-nav-head">
                    <h3>审批分组</h3>
                  </div>
                  <button
                    v-for="item in dashboardNavItems"
                    :key="item.key"
                    class="oa-lite-center-nav-item"
                    :class="{ active: activeTab === item.key }"
                    @click="openTab(item.key)"
                  >
                    <span class="oa-lite-center-nav-main">
                      <span class="oa-lite-center-nav-icon">
                        <IconifyIcon :icon="item.icon" />
                      </span>
                      <span class="oa-lite-center-nav-text">{{ item.label }}</span>
                    </span>
                    <Tag class="oa-lite-center-nav-count">{{ item.count }}</Tag>
                  </button>
                </aside>

                <div class="oa-lite-center-content">
                  <div class="oa-lite-list-panel">
                    <div class="oa-lite-list-headline">
                      <div>
                        <div class="oa-lite-section-title">{{ currentListTitle }}</div>
                      </div>
                      <div class="oa-lite-list-toolbar">
                        <span class="oa-lite-list-total">
                          {{ currentPageState?.total || currentList.length }} 条记录
                        </span>
                        <span class="oa-lite-toolbar-divider" />
                        <Button type="link" @click="resetCurrentFilter">重置筛选</Button>
                      </div>
                    </div>

                    <div class="oa-lite-filter-shell">
                      <div class="oa-lite-filters">
                        <Input
                          v-model:value="currentFilter!.name"
                          :placeholder="getKeywordPlaceholder()"
                          allow-clear
                          @press-enter="handleFilterSubmit"
                        >
                          <template #prefix>
                            <IconifyIcon icon="solar:magnifer-outline" />
                          </template>
                        </Input>

                        <Select
                          v-if="showProcessFilter"
                          v-model:value="currentProcessFilterValue"
                          class="oa-lite-filter-control"
                          placeholder="流程模板"
                          allow-clear
                          :options="currentProcessOptions"
                          popup-class-name="oa-lite-status-popup"
                          :get-popup-container="(triggerNode) => triggerNode.parentNode"
                        />

                        <Select
                          v-if="showCategoryFilter"
                          v-model:value="currentFilter!.category"
                          class="oa-lite-filter-control"
                          placeholder="流程分类"
                          allow-clear
                          :options="categoryOptions"
                          popup-class-name="oa-lite-status-popup"
                          :get-popup-container="(triggerNode) => triggerNode.parentNode"
                        />

                        <Select
                          v-if="showStatusFilter"
                          v-model:value="currentFilter!.status"
                          class="oa-lite-filter-control"
                          :placeholder="activeTab === 'processed' ? '审批状态' : '流程状态'"
                          allow-clear
                          :options="currentStatusOptions"
                          popup-class-name="oa-lite-status-popup"
                          :get-popup-container="(triggerNode) => triggerNode.parentNode"
                        />

                        <DatePicker.RangePicker
                          v-model:value="currentFilter!.createTime"
                          class="oa-lite-filter-range"
                          show-time
                          value-format="YYYY-MM-DD HH:mm:ss"
                          format="YYYY-MM-DD HH:mm:ss"
                          :placeholder="getCreateTimePlaceholder()"
                        />
                      </div>

                      <div class="oa-lite-filter-actions">
                        <Button type="primary" @click="handleFilterSubmit">查询</Button>
                        <Button class="oa-lite-white-button" @click="resetCurrentFilter">
                          重置
                        </Button>
                      </div>
                    </div>

                    <div class="oa-lite-list-scroll-region">
                      <Spin :spinning="currentListLoading" class="oa-lite-list-spin">
                        <div v-if="currentList.length > 0" class="oa-lite-list-scroll-body">
                          <div class="oa-lite-list">
                            <button
                              v-for="item in currentList"
                              :key="getItemIdentity(item)"
                              class="oa-lite-list-item"
                              :class="{ active: selectedItem === item }"
                              @click="selectedItem = item"
                            >
                              <div class="oa-lite-list-main">
                                <div class="oa-lite-list-head">
                                  <div class="oa-lite-list-title-wrap">
                                    <div class="oa-lite-list-title">{{ getItemTitle(item) }}</div>
                                    <div class="oa-lite-list-primary-meta">{{ getItemMetaLeft(item) }}</div>
                                  </div>
                                  <span class="oa-lite-list-date">{{ getItemMetaRight(item) }}</span>
                                </div>
                                <div v-if="getListSecondaryText(item)" class="oa-lite-list-summary">
                                  {{ getListSecondaryText(item) }}
                                </div>
                              </div>
                              <div class="oa-lite-list-side">
                                <Tag
                                  v-if="getItemStatus(item) !== undefined"
                                  class="oa-lite-list-status-tag"
                                  :class="`tone-${getItemStatusTone(item)}`"
                                >
                                  {{ getItemStatusText(item) }}
                                </Tag>
                              </div>
                            </button>
                          </div>
                        </div>
                        <div v-else class="oa-lite-list-empty">
                          <Empty :description="`暂无${currentListTitle}数据`" />
                        </div>
                      </Spin>
                    </div>

                    <div
                      v-if="currentPageState && currentPageState.total > 0"
                      class="oa-lite-pagination-wrap"
                    >
                      <Pagination
                        :current="currentPageState.pageNo"
                        :page-size="currentPageState.pageSize"
                        :total="currentPageState.total"
                        :show-size-changer="true"
                        :show-total="(total) => `共 ${total} 条`"
                        @change="handlePageChange"
                      />
                    </div>
                  </div>

                  <div class="oa-lite-detail-panel">
                    <div class="oa-lite-detail-panel-head">
                      <div>
                        <div class="oa-lite-section-title">流程详情</div>
                      </div>
                    </div>
                    <div v-if="currentDetailRequest" class="oa-lite-detail-scroll-region">
                      <ProcessDetail
                        :request="currentDetailRequest"
                        :section="currentDetailSection"
                        @refresh="handleDetailRefresh"
                        @recreate="handleProcessRecreate"
                      />
                    </div>
                    <div v-else class="oa-lite-detail-empty">
                      <Empty :description="`请选择要查看的${currentListTitle}详情`" />
                    </div>
                  </div>
                </div>
              </section>
            </template>
          </div>
        </Spin>
      </main>
    </div>
  </ConfigProvider>
</template>

<style lang="scss" scoped>
.oa-lite-page {
  min-height: 100vh;
  background: var(--oa-shell-bg);
  color: var(--oa-ink);
  position: relative;
}

.oa-lite-page :deep(.bg-card),
.oa-lite-page :deep(.bg-background),
.oa-lite-page :deep(.bg-popover) {
  background: var(--oa-shell-surface) !important;
}

.oa-lite-page :deep(.bg-background-deep) {
  background: var(--oa-shell-bg) !important;
}

.oa-lite-page :deep(.bg-accent),
.oa-lite-page :deep(.bg-muted),
.oa-lite-page :deep(.bg-secondary),
.oa-lite-page :deep(.bg-gray-100),
.oa-lite-page :deep(.dark\:bg-gray-600) {
  background: var(--oa-shell-surface-muted) !important;
}

.oa-lite-page :deep(.border-border) {
  border-color: var(--oa-shell-border) !important;
}

.oa-lite-page :deep(.text-foreground),
.oa-lite-page :deep(.text-card-foreground),
.oa-lite-page :deep(.text-popover-foreground),
.oa-lite-page :deep(.text-accent-foreground) {
  color: var(--oa-ink) !important;
}

.oa-lite-page :deep(.text-muted-foreground),
.oa-lite-page :deep(.text-gray-500),
.oa-lite-page :deep([class~='text-foreground/80']),
.oa-lite-page :deep([class~='text-foreground/60']) {
  color: var(--oa-ink-soft) !important;
}

.oa-lite-page :deep(.ant-empty-description),
.oa-lite-page :deep(.ant-spin-text),
.oa-lite-page :deep(.ant-pagination-total-text),
.oa-lite-page :deep(.ant-pagination .ant-pagination-item a),
.oa-lite-page :deep(.ant-select-selection-item),
.oa-lite-page :deep(.ant-select-selection-search-input),
.oa-lite-page :deep(.ant-picker-input > input),
.oa-lite-page :deep(.ant-form-item-label > label),
.oa-lite-page :deep(.ant-alert-message),
.oa-lite-page :deep(.ant-alert-description),
.oa-lite-page :deep(.ant-input-prefix),
.oa-lite-page :deep(.ant-input-show-count-suffix),
.oa-lite-page :deep(.ant-picker-suffix),
.oa-lite-page :deep(.ant-picker-clear),
.oa-lite-page :deep(.ant-select-arrow),
.oa-lite-page :deep(.ant-select-clear) {
  color: var(--oa-ink) !important;
}

.oa-lite-page :deep(.ant-form-item-extra),
.oa-lite-page :deep(.ant-form-item-explain),
.oa-lite-page :deep(.ant-pagination-options),
.oa-lite-page :deep(.ant-empty-normal) {
  color: var(--oa-ink-soft) !important;
}

.oa-lite-page :deep(.ant-btn:not(.ant-btn-primary):not(.ant-btn-dangerous)),
.oa-lite-page :deep(.ant-btn:not(.ant-btn-primary):not(.ant-btn-dangerous) > span),
.oa-lite-page :deep(.ant-btn-link),
.oa-lite-page :deep(.ant-btn-link > span) {
  color: var(--oa-ink) !important;
}

.oa-lite-bg {
  position: fixed;
  inset: 0 auto auto 0;
  width: 100%;
  height: 220px;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--oa-shell-surface-subtle) 82%, transparent) 0%,
      color-mix(in srgb, var(--oa-shell-surface-subtle) 34%, transparent) 92px,
      transparent 100%
    );
  pointer-events: none;
  z-index: 0;
  opacity: 1;
}

:global(body.oa-lite-theme-dark) .oa-lite-bg {
  background:
    linear-gradient(
      180deg,
      rgb(10 18 28 / 68%) 0%,
      rgb(10 18 28 / 20%) 92px,
      transparent 100%
    );
}

.oa-lite-topbar,
.oa-lite-main,
.oa-lite-leave-page {
  position: relative;
  z-index: 1;
}

.oa-lite-topbar {
  padding: 14px 24px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
}

.oa-lite-topbar-inner {
  max-width: 1260px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 28px;
  min-height: 58px;
}

.oa-lite-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.oa-lite-brand-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  color: var(--oa-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.oa-lite-brand-title {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.oa-lite-brand-subtitle {
  margin-top: 2px;
  color: var(--oa-ink-faint);
  font-size: 12px;
}

.oa-lite-topnav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 28px;
}

.oa-lite-topnav-tab {
  position: relative;
  border: none;
  background: transparent;
  padding: 6px 0 12px;
  color: var(--oa-ink-soft);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.18s ease;
}

.oa-lite-topnav-tab:hover,
.oa-lite-topnav-tab.active {
  color: var(--oa-ink);
}

.oa-lite-topnav-tab.active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: var(--oa-accent);
}

.oa-lite-user-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.oa-lite-refresh-button {
  white-space: nowrap;
}

.oa-lite-header-widget-bar {
  display: flex;
  align-items: center;
  padding: 0 0 0 10px;
  border-left: 1px solid var(--oa-shell-border);
  background: transparent;
}

.oa-lite-header-widget-bar :deep(.text-foreground),
.oa-lite-header-widget-bar :deep(.text-muted-foreground),
.oa-lite-header-widget-bar :deep(.anticon),
.oa-lite-header-widget-bar :deep(svg) {
  color: var(--oa-ink) !important;
}

.oa-lite-header-widget-bar :deep(.mr-1),
.oa-lite-header-widget-bar :deep(.mr-2) {
  margin-right: 4px !important;
}

.oa-lite-header-widget-bar :deep(.ml-1) {
  margin-left: 0 !important;
}

.oa-lite-header-widget-bar :deep(.hover\:bg-accent:hover),
.oa-lite-header-widget-bar :deep(.hover\:text-accent-foreground:hover) {
  color: var(--oa-ink) !important;
}

.oa-lite-header-user :deep(.mr-2) {
  margin-right: 0 !important;
}

.oa-lite-main {
  padding: 20px 24px 32px;
}

.oa-lite-main-embedded {
  padding-top: 6px;
}

.oa-lite-main.is-center-mode {
  padding-right: 0;
  padding-left: 0;
}

.oa-lite-home-shell {
  max-width: 1260px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.oa-lite-home-shell.is-center-mode {
  max-width: none;
  margin: 0;
}

.oa-lite-stat-pillar {
  align-self: stretch;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 92%, white);
  border-radius: 18px;
  background: linear-gradient(180deg, rgb(255 255 255 / 98%) 0%, rgb(248 250 252 / 98%) 100%);
  box-shadow: 0 8px 22px rgb(15 23 42 / 4%);
}

:global(body.oa-lite-theme-dark) .oa-lite-stat-pillar {
  border-color: var(--oa-shell-border);
  background: linear-gradient(
    180deg,
    var(--oa-shell-surface) 0%,
    var(--oa-shell-surface-muted) 100%
  );
  box-shadow: none;
}

.oa-lite-stat-item {
  border: none;
  background: transparent;
  padding: 22px 20px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-areas:
    'icon count arrow'
    'icon label arrow';
  align-items: center;
  gap: 3px 14px;
  color: color-mix(in srgb, var(--oa-ink-soft) 88%, var(--oa-ink));
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.oa-lite-stat-item + .oa-lite-stat-item {
  border-left: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, white);
}

:global(body.oa-lite-theme-dark) .oa-lite-stat-item + .oa-lite-stat-item {
  border-left-color: color-mix(in srgb, var(--oa-shell-border) 76%, transparent);
}

.oa-lite-stat-item:hover {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-accent-soft) 28%, white) 0%,
    color-mix(in srgb, var(--oa-accent-soft) 44%, white) 100%
  );
  color: var(--oa-accent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--oa-accent) 14%, white);
}

:global(body.oa-lite-theme-dark) .oa-lite-stat-item:hover {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-accent-soft) 14%, var(--oa-shell-surface)) 0%,
    color-mix(in srgb, var(--oa-accent-soft) 22%, var(--oa-shell-surface-muted)) 100%
  );
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--oa-accent) 18%, transparent);
}

.oa-lite-stat-count {
  grid-area: count;
  min-width: 0;
  height: auto;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--oa-ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}

.oa-lite-stat-item:hover .oa-lite-stat-count {
  background: transparent;
  color: var(--oa-accent);
}

.oa-lite-stat-icon,
.oa-lite-stat-arrow {
  color: var(--oa-ink-faint);
  font-size: 15px;
}

.oa-lite-stat-icon {
  grid-area: icon;
  width: 38px;
  height: 38px;
  align-self: center;
  justify-self: start;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 90%, white);
  border-radius: 12px;
  background: linear-gradient(180deg, rgb(255 255 255 / 98%) 0%, rgb(241 245 249 / 98%) 100%);
  color: color-mix(in srgb, var(--oa-ink-soft) 82%, var(--oa-ink));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 88%);
}

.oa-lite-stat-item:hover .oa-lite-stat-icon {
  border-color: color-mix(in srgb, var(--oa-accent) 18%, white);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-accent-soft) 52%, white) 0%,
    color-mix(in srgb, var(--oa-accent-soft) 74%, white) 100%
  );
  color: var(--oa-accent);
}

:global(body.oa-lite-theme-dark) .oa-lite-stat-icon {
  border-color: color-mix(in srgb, var(--oa-shell-border) 78%, transparent);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-shell-surface-muted) 92%, black) 0%,
    color-mix(in srgb, var(--oa-shell-surface) 92%, black) 100%
  );
  color: var(--oa-ink-soft);
}

.oa-lite-stat-arrow {
  grid-area: arrow;
  justify-self: end;
}

.oa-lite-stat-item:hover .oa-lite-stat-arrow,
.oa-lite-stat-item:hover .oa-lite-stat-label {
  color: var(--oa-accent);
}

.oa-lite-stat-label {
  grid-area: label;
  font-size: 14px;
  font-weight: 500;
  min-width: 0;
}

.oa-lite-create-shell {
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 18px 20px 8px;
  border: 1px solid var(--oa-shell-border);
  border-radius: 16px;
  background: var(--oa-shell-surface);
}

.oa-lite-create-sections {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.oa-lite-profile-shell {
  width: 100%;
  max-width: 1260px;
}

.oa-lite-profile-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.oa-lite-profile-content {
  border-top: 1px solid var(--oa-shell-border);
  background: transparent;
  box-shadow: none;
  padding: 20px 0 0;
}

.oa-lite-profile-content :deep(.ant-card) {
  border-color: var(--oa-shell-border) !important;
  border-radius: 0 !important;
  box-shadow: none !important;
}

.oa-lite-profile-content :deep(.ant-card-head) {
  border-bottom-color: var(--oa-shell-border) !important;
}

.oa-lite-profile-content :deep(.ant-tabs-nav::before) {
  border-bottom-color: var(--oa-shell-border) !important;
}

.oa-lite-create-toolbar {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  padding: 0 0 14px;
  background: var(--oa-shell-surface);
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 76%, transparent);
}

.oa-lite-category-tabs {
  display: flex;
  align-items: center;
  gap: 24px;
  width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
}

.oa-lite-category-tabs::-webkit-scrollbar {
  display: none;
}

.oa-lite-category-tab {
  position: relative;
  border: none;
  background: var(--oa-shell-surface-muted);
  padding: 8px 12px;
  color: var(--oa-ink-soft);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  border-radius: 10px;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}

.oa-lite-category-tab:hover,
.oa-lite-category-tab.active {
  color: var(--oa-accent);
  background: var(--oa-accent-soft);
}

.oa-lite-category-tab.active::after {
  display: none;
}

.oa-lite-template-section {
  scroll-margin-top: 128px;
}

.oa-lite-template-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-lite-template-section-title {
  font-size: 16px;
  color: var(--oa-ink);
  font-weight: 600;
}

.oa-lite-template-section-arrow {
  color: var(--oa-ink-faint);
  font-size: 14px;
}

.oa-lite-template-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px 14px;
  border-top: 0;
}

.oa-lite-template-card {
  min-height: 78px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 92%, transparent);
  background: var(--oa-shell-surface-raised);
  border-radius: 14px;
  padding: 16px 14px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease;
}

.oa-lite-template-card:hover {
  background: color-mix(in srgb, var(--oa-accent-soft) 42%, white);
  border-color: color-mix(in srgb, var(--oa-accent) 22%, var(--oa-shell-border));
}

:global(body.oa-lite-theme-dark) .oa-lite-template-card:hover {
  background: color-mix(in srgb, var(--oa-accent-soft) 42%, var(--oa-shell-surface-muted));
}

.oa-lite-template-card:disabled {
  cursor: wait;
  opacity: 0.82;
}

.oa-lite-template-icon {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 10px;
  background: color-mix(in srgb, var(--oa-accent-soft) 84%, white);
  color: var(--oa-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 0;
}

:global(body.oa-lite-theme-dark) .oa-lite-template-icon {
  background: color-mix(in srgb, var(--oa-accent-soft) 62%, var(--oa-shell-surface-muted));
}

.oa-lite-template-body {
  min-width: 0;
}

.oa-lite-template-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--oa-ink);
  line-height: 1.45;
}

.oa-lite-template-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--oa-ink-soft);
  line-height: 1.5;
}

.oa-lite-center-shell {
  --oa-lite-center-panel-height: calc(100dvh - 150px);
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.oa-lite-center-nav {
  padding: 0 16px 0 20px;
  border-right: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
}

.oa-lite-center-nav-head {
  padding: 4px 0 18px;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
}

.oa-lite-center-nav-head h3 {
  margin: 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.oa-lite-center-nav-head p {
  margin: 10px 0 0;
  color: var(--oa-ink-soft);
  font-size: 12px;
  line-height: 1.7;
}

.oa-lite-center-nav-item {
  width: 100%;
  margin: 0;
  border: none;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
  border-radius: 0;
  background: transparent;
  padding: 13px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--oa-ink-soft);
  cursor: pointer;
  transition:
    padding-left 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease;
  position: relative;
}

.oa-lite-center-nav-item:hover {
  color: var(--oa-ink);
}

.oa-lite-center-nav-item.active {
  color: var(--oa-accent);
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 34%, var(--oa-shell-border));
  padding-left: 12px;
}

.oa-lite-center-nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: var(--oa-accent);
}

.oa-lite-center-nav-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.oa-lite-center-nav-icon {
  font-size: 16px;
  color: inherit;
  display: inline-flex;
  align-items: center;
}

.oa-lite-center-nav-text {
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.oa-lite-center-nav-count.ant-tag {
  min-width: 0;
  height: auto;
  padding: 0;
  margin-inline-end: 0;
  border-radius: 0;
  border: 0;
  background: transparent !important;
  color: var(--oa-ink-faint) !important;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
  line-height: 1;
}

.oa-lite-center-content {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 20px;
  min-height: var(--oa-lite-center-panel-height);
  align-items: stretch;
}

.oa-lite-list-panel,
.oa-lite-detail-panel {
  height: var(--oa-lite-center-panel-height);
  background: transparent;
  border: 0;
  border-radius: 0;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.oa-lite-list-panel {
  padding: 0 18px 0 0;
  border-right: 1px solid var(--oa-shell-border);
}

.oa-lite-detail-panel {
  padding: 0 0 0 2px;
}

.oa-lite-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 2px;
  padding: 2px 4px 0;
}

.oa-lite-list-header {
  margin-bottom: 16px;
}

.oa-lite-list-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
  margin-bottom: 16px;
}

.oa-lite-list-hero-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--oa-ink-soft);
  font-size: 13px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}

.oa-lite-section-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-filters {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.oa-lite-filter-control,
.oa-lite-filter-range {
  width: 100%;
}

.oa-lite-filter-shell {
  margin-bottom: 16px;
  padding: 0 0 14px;
  border-bottom: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
}

.oa-lite-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 12px;
  flex-shrink: 0;
}

.oa-lite-list-scroll-region {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
}

.oa-lite-list-spin {
  display: flex;
  flex: 1;
  min-height: 0;
}

.oa-lite-list-spin :deep(.ant-spin-nested-loading),
.oa-lite-list-spin :deep(.ant-spin-container) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: visible;
}

.oa-lite-list-scroll-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: visible;
}

.oa-lite-list {
  display: flex;
  flex-direction: column;
  flex: none;
  min-height: 100%;
  min-width: 100%;
  overflow: visible;
  padding-right: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.oa-lite-list-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.oa-lite-list-item {
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--oa-shell-border);
  background: transparent;
  border-radius: 0;
  text-align: left;
  padding: 8px 0;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  position: relative;
}

.oa-lite-list-item:last-child {
  border-bottom: 0;
}

.oa-lite-list-item:hover {
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 18%, var(--oa-shell-border));
}

.oa-lite-list-item.active {
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 34%, var(--oa-shell-border));
}

.oa-lite-list-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--oa-accent);
}

.oa-lite-list-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.oa-lite-list-title-wrap {
  min-width: 0;
  flex: 1;
}

.oa-lite-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.oa-lite-list-title {
  overflow: hidden;
  color: var(--oa-ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-lite-list-primary-meta {
  overflow: hidden;
  margin-top: 2px;
  color: var(--oa-ink-soft);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-lite-list-date {
  max-width: 152px;
  font-size: 11px;
  color: var(--oa-ink-faint);
  white-space: nowrap;
  flex: none;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
  overflow: hidden;
  text-align: right;
  text-overflow: ellipsis;
}

.oa-lite-list-summary {
  overflow: hidden;
  font-size: 11px;
  line-height: 1.35;
  color: var(--oa-ink-soft);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-lite-list-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  align-self: center;
}

.oa-lite-list-status-tag.ant-tag {
  margin-inline-end: 0;
  padding: 0;
  border-radius: 0;
  border: 0;
  border-bottom: 1px solid var(--oa-shell-border);
  background: transparent !important;
  color: var(--oa-ink) !important;
  line-height: 1.5;
  font-weight: 600;
}

.oa-lite-list-status-tag.ant-tag.tone-success {
  background: transparent !important;
  border-bottom-color: color-mix(in srgb, var(--oa-success) 44%, var(--oa-shell-border)) !important;
  color: var(--oa-success-text) !important;
}

.oa-lite-list-status-tag.ant-tag.tone-warning {
  background: transparent !important;
  border-bottom-color: color-mix(in srgb, var(--oa-warning-text) 44%, var(--oa-shell-border)) !important;
  color: var(--oa-warning-text) !important;
}

.oa-lite-list-status-tag.ant-tag.tone-danger {
  background: transparent !important;
  border-bottom-color: color-mix(in srgb, var(--oa-danger-text) 44%, var(--oa-shell-border)) !important;
  color: var(--oa-danger-text) !important;
}

.oa-lite-list-status-tag.ant-tag.tone-muted {
  background: transparent !important;
  border-bottom-color: color-mix(in srgb, var(--oa-ink-faint) 34%, var(--oa-shell-border)) !important;
  color: var(--oa-ink-soft) !important;
}

.oa-lite-list-status-tag.ant-tag.tone-neutral {
  background: transparent !important;
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 44%, var(--oa-shell-border)) !important;
  color: var(--oa-accent) !important;
}

.oa-lite-pagination-wrap {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.oa-lite-detail-scroll-region {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.oa-lite-detail-panel-head {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
  margin-bottom: 16px;
}

.oa-lite-detail-empty {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.oa-lite-white-button {
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  background: transparent;
  border: 1px solid var(--oa-shell-border);
  color: var(--oa-ink);
  box-shadow: none;
}

.oa-lite-leave-page {
  min-height: 100vh;
  background: var(--oa-shell-bg);
  display: flex;
  flex-direction: column;
}

.oa-lite-leave-header {
  height: 56px;
  background: var(--oa-shell-surface);
  border-bottom: 1px solid var(--oa-shell-border);
  display: flex;
  align-items: center;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 20;
}

.oa-lite-leave-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.oa-lite-leave-back {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--oa-ink-soft);
  cursor: pointer;
}

.oa-lite-leave-header-tabs {
  display: flex;
  align-items: center;
  gap: 24px;
  height: 100%;
}

.oa-lite-leave-header-tab {
  height: 56px;
  display: flex;
  align-items: center;
  font-size: 15px;
  color: var(--oa-ink);
  font-weight: 600;
  position: relative;
}

.oa-lite-leave-header-tab.active::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  width: 24px;
  height: 3px;
  border-radius: 999px;
  background: var(--oa-accent);
}

.oa-lite-leave-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0 80px;
}

.oa-lite-leave-shell {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.oa-lite-leave-card {
  background: var(--oa-shell-surface);
  border-radius: 16px;
  border: 1px solid var(--oa-shell-border);
  box-shadow: none;
  padding: 32px;
}

.oa-lite-leave-title-row {
  position: relative;
}

.oa-lite-leave-title {
  margin: 0;
  font-size: 30px;
  font-weight: 700;
  color: var(--oa-ink);
}

.oa-lite-leave-subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--oa-ink-faint);
}

.oa-lite-leave-qr {
  position: absolute;
  top: 0;
  right: 0;
  font-size: 32px;
  color: var(--oa-shell-border-strong);
}

.oa-lite-leave-divider {
  border-bottom: 1px dashed var(--oa-shell-border);
  padding-top: 14px;
  margin-bottom: 12px;
}

.oa-lite-leave-card :deep(.ant-form-item-label > label) {
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-lite-leave-card :deep(.ant-input),
.oa-lite-leave-card :deep(.ant-input-affix-wrapper),
.oa-lite-leave-card :deep(.ant-picker),
.oa-lite-leave-card :deep(.ant-select-selector),
.oa-lite-leave-card :deep(textarea.ant-input),
.oa-lite-list-panel :deep(.ant-input),
.oa-lite-list-panel :deep(.ant-input-affix-wrapper),
.oa-lite-list-panel :deep(.ant-picker),
.oa-lite-list-panel :deep(.ant-select-selector),
.oa-lite-list-panel :deep(textarea.ant-input),
.oa-lite-detail-panel :deep(.ant-input),
.oa-lite-detail-panel :deep(.ant-input-affix-wrapper),
.oa-lite-detail-panel :deep(.ant-picker),
.oa-lite-detail-panel :deep(.ant-select-selector),
.oa-lite-detail-panel :deep(textarea.ant-input) {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
  border: 1px solid var(--oa-shell-border) !important;
  box-shadow: none !important;
}

.oa-lite-leave-card :deep(.ant-input::placeholder),
.oa-lite-leave-card :deep(textarea.ant-input::placeholder),
.oa-lite-leave-card :deep(.ant-select-selection-placeholder),
.oa-lite-leave-card :deep(.ant-picker-input input::placeholder),
.oa-lite-list-panel :deep(.ant-input::placeholder),
.oa-lite-list-panel :deep(textarea.ant-input::placeholder),
.oa-lite-list-panel :deep(.ant-select-selection-placeholder),
.oa-lite-list-panel :deep(.ant-picker-input input::placeholder),
.oa-lite-detail-panel :deep(.ant-input::placeholder),
.oa-lite-detail-panel :deep(textarea.ant-input::placeholder),
.oa-lite-detail-panel :deep(.ant-select-selection-placeholder),
.oa-lite-detail-panel :deep(.ant-picker-input input::placeholder) {
  color: var(--oa-ink-faint) !important;
}

.oa-lite-leave-card :deep(.ant-picker-input > input),
.oa-lite-leave-card :deep(.ant-select-selection-item),
.oa-lite-leave-card :deep(.ant-select-arrow),
.oa-lite-leave-card :deep(.ant-picker-suffix),
.oa-lite-leave-card :deep(.ant-picker-clear),
.oa-lite-list-panel :deep(.ant-picker-input > input),
.oa-lite-list-panel :deep(.ant-select-selection-item),
.oa-lite-list-panel :deep(.ant-select-arrow),
.oa-lite-list-panel :deep(.ant-picker-suffix),
.oa-lite-list-panel :deep(.ant-picker-clear),
.oa-lite-detail-panel :deep(.ant-picker-input > input),
.oa-lite-detail-panel :deep(.ant-select-selection-item),
.oa-lite-detail-panel :deep(.ant-select-arrow),
.oa-lite-detail-panel :deep(.ant-picker-suffix),
.oa-lite-detail-panel :deep(.ant-picker-clear) {
  color: var(--oa-ink) !important;
}

.oa-lite-leave-card :deep(.ant-input:focus),
.oa-lite-leave-card :deep(.ant-input-affix-wrapper-focused),
.oa-lite-leave-card :deep(.ant-picker-focused),
.oa-lite-leave-card :deep(.ant-select-focused .ant-select-selector),
.oa-lite-leave-card :deep(textarea.ant-input:focus),
.oa-lite-list-panel :deep(.ant-input:focus),
.oa-lite-list-panel :deep(.ant-input-affix-wrapper-focused),
.oa-lite-list-panel :deep(.ant-picker-focused),
.oa-lite-list-panel :deep(.ant-select-focused .ant-select-selector),
.oa-lite-list-panel :deep(textarea.ant-input:focus),
.oa-lite-detail-panel :deep(.ant-input:focus),
.oa-lite-detail-panel :deep(.ant-input-affix-wrapper-focused),
.oa-lite-detail-panel :deep(.ant-picker-focused),
.oa-lite-detail-panel :deep(.ant-select-focused .ant-select-selector),
.oa-lite-detail-panel :deep(textarea.ant-input:focus) {
  border-color: var(--oa-accent) !important;
  box-shadow: var(--oa-focus-ring) !important;
}

:deep(.oa-lite-select-popup.ant-select-dropdown),
:deep(.oa-lite-status-popup.ant-select-dropdown) {
  background: var(--oa-shell-surface) !important;
  border: 1px solid var(--oa-shell-border) !important;
  box-shadow: var(--oa-shell-shadow) !important;
  border-radius: 16px !important;
  padding: 8px 0 !important;
}

:deep(.oa-lite-select-popup .ant-select-item),
:deep(.oa-lite-status-popup .ant-select-item) {
  color: var(--oa-ink) !important;
  background: var(--oa-shell-surface) !important;
}

:deep(.oa-lite-select-popup .ant-select-item-option-active:not(.ant-select-item-option-disabled)),
:deep(.oa-lite-status-popup .ant-select-item-option-active:not(.ant-select-item-option-disabled)) {
  background: var(--oa-shell-surface-muted) !important;
}

:deep(.oa-lite-select-popup .ant-select-item-option-selected:not(.ant-select-item-option-disabled)),
:deep(.oa-lite-status-popup .ant-select-item-option-selected:not(.ant-select-item-option-disabled)) {
  background: var(--oa-accent-soft) !important;
  color: var(--oa-accent) !important;
}

.oa-lite-leave-flow-head {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--oa-shell-border);
  padding-bottom: 16px;
}

.oa-lite-leave-flow-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--oa-ink);
}

.oa-lite-leave-flow-tag {
  margin-left: 12px;
  font-size: 12px;
  color: var(--oa-accent);
}

.oa-lite-leave-flow-body {
  position: relative;
  padding-top: 18px;
  padding-left: 18px;

  :deep(.ant-timeline) {
    margin: 0;
    padding-top: 0 !important;
  }

  :deep(.ant-timeline-item-content) {
    color: var(--oa-ink);
  }

  :deep(.font-bold) {
    color: var(--oa-ink);
    font-weight: 700;
  }

  :deep(.text-sm) {
    color: var(--oa-ink-soft);
  }

  :deep(.text-gray-500) {
    color: var(--oa-ink-faint) !important;
  }

  :deep(.bg-gray-100) {
    background: var(--oa-shell-surface-muted) !important;
    color: var(--oa-ink) !important;
  }

  :deep(.dark\:bg-gray-600) {
    background: var(--oa-shell-surface-muted) !important;
  }

  :deep(.ant-btn.ant-btn-icon-only.ant-btn-background-ghost.ant-btn-primary) {
    width: auto;
    min-width: 116px;
    height: 36px;
    padding: 0 14px;
    border-radius: 12px;
    border-color: var(--oa-shell-border);
    background: var(--oa-shell-surface);
    color: var(--oa-ink);
    box-shadow: none;
  }

  :deep(.ant-btn.ant-btn-icon-only.ant-btn-background-ghost.ant-btn-primary::after) {
    content: v-bind(selectApproverLabel);
    margin-left: 6px;
    font-size: 13px;
    font-weight: 600;
    color: var(--oa-ink);
  }

  :deep(.ant-btn.ant-btn-icon-only.ant-btn-background-ghost.ant-btn-primary:hover) {
    border-color: var(--oa-shell-border-strong);
    color: var(--oa-accent);
  }

  :deep(.ant-btn.ant-btn-icon-only.ant-btn-background-ghost.ant-btn-primary:hover::after) {
    color: var(--oa-accent);
  }
}

.oa-lite-leave-flow-line {
  position: absolute;
  top: 26px;
  bottom: 34px;
  left: 21px;
  width: 1px;
  background: var(--oa-shell-border);
}

.oa-lite-leave-flow-node {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 22px;
  margin-bottom: 30px;
}

.oa-lite-leave-flow-node-last {
  margin-bottom: 0;
}

.oa-lite-leave-flow-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: var(--oa-shell-border-strong);
  box-shadow: 0 0 0 4px var(--oa-shell-surface);
  position: relative;
  left: -3px;
  z-index: 2;
  flex-shrink: 0;
  margin-top: 4px;
}

.oa-lite-leave-node-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-leave-node-subtitle {
  margin-top: 2px;
  font-size: 11px;
  color: var(--oa-ink-faint);
}

.oa-lite-leave-node-body {
  min-width: 0;
}

.oa-lite-leave-node-select {
  width: 220px;
  margin-top: 12px;
}

.oa-lite-leave-submit-row {
  padding-top: 20px;
}

@media (max-width: 1000px) {
  .oa-lite-topbar-inner {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .oa-lite-user-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }

  .oa-lite-template-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1024px) {
  .oa-lite-topbar-inner {
    grid-template-columns: 1fr;
    justify-items: start;
  }

  .oa-lite-topnav {
    justify-content: flex-start;
  }

  .oa-lite-center-shell,
  .oa-lite-center-content {
    grid-template-columns: 1fr;
  }

  .oa-lite-center-shell {
    --oa-lite-center-panel-height: auto;
  }

  .oa-lite-center-nav {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0;
    padding: 0;
    border-right: 0;
    border-bottom: 1px solid var(--oa-shell-border);
  }

  .oa-lite-center-nav-item {
    width: 100%;
    margin: 0;
  }

  .oa-lite-template-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .oa-lite-list-panel,
  .oa-lite-detail-panel {
    height: auto;
  }

  .oa-lite-list-scroll-region,
  .oa-lite-list-scroll-body,
  .oa-lite-list,
  .oa-lite-detail-scroll-region {
    height: auto;
    max-height: none;
    overflow: visible;
  }

  .oa-lite-detail-empty {
    min-height: 320px;
  }
}

@media (max-width: 768px) {
  .oa-lite-topbar {
    padding: 16px 14px 0;
  }

  .oa-lite-main {
    padding: 14px 14px 20px;
  }

  .oa-lite-stat-pillar {
    width: 100%;
    display: flex;
    flex-wrap: nowrap;
    justify-content: flex-start;
    overflow-x: auto;
    border-top: 0;
  }

  .oa-lite-stat-item {
    flex: 0 0 auto;
    display: inline-flex;
    padding-right: 18px;
  }

  .oa-lite-center-nav {
    grid-template-columns: 1fr;
  }

  .oa-lite-create-search {
    display: none;
  }

  .oa-lite-list-panel,
  .oa-lite-detail-panel {
    padding: 16px;
    border-radius: 0;
  }

  .oa-lite-template-grid {
    grid-template-columns: 1fr;
  }

  .oa-lite-section-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .oa-lite-list-item {
    grid-template-columns: 1fr;
  }

  .oa-lite-list-head {
    flex-direction: column;
  }

  .oa-lite-list-side {
    justify-content: flex-start;
  }

  .oa-lite-leave-shell {
    padding: 0 14px;
  }

  .oa-lite-leave-card {
    padding: 20px;
  }
}
</style>

<style lang="scss">
body.oa-lite-theme-light {
  --background: 0 0% 100%;
  --background-deep: 216 20.11% 95.47%;
  --foreground: 210 6% 21%;
  --muted: 240 4.8% 95.9%;
  --muted-foreground: 240 3.8% 46.1%;
  --accent: 240 5% 96%;
  --accent-hover: 200deg 10% 90%;
  --accent-foreground: 240 6% 10%;
  --border: 240 5.9% 90%;
}

body.oa-lite-theme-light .z-popup,
body.oa-lite-theme-light [role='dialog'],
body.oa-lite-theme-light [role='menu'],
body.oa-lite-theme-dark .z-popup,
body.oa-lite-theme-dark [role='dialog'],
body.oa-lite-theme-dark [role='menu'] {
  background: var(--oa-shell-surface) !important;
  border-color: var(--oa-shell-border) !important;
  color: var(--oa-ink) !important;
  box-shadow: var(--oa-shell-shadow) !important;
}

body.oa-lite-theme-light .z-popup .bg-popover,
body.oa-lite-theme-light .z-popup .bg-background,
body.oa-lite-theme-light .z-popup .bg-card,
body.oa-lite-theme-light .z-popup .text-popover-foreground,
body.oa-lite-theme-light .z-popup .text-foreground,
body.oa-lite-theme-light .z-popup .text-card-foreground,
body.oa-lite-theme-light .z-popup .text-muted-foreground,
body.oa-lite-theme-light [role='dialog'] .bg-popover,
body.oa-lite-theme-light [role='dialog'] .bg-background,
body.oa-lite-theme-light [role='dialog'] .bg-card,
body.oa-lite-theme-light [role='menu'] .bg-popover,
body.oa-lite-theme-light [role='menu'] .bg-background,
body.oa-lite-theme-light [role='menu'] .bg-card,
body.oa-lite-theme-dark .z-popup .bg-popover,
body.oa-lite-theme-dark .z-popup .bg-background,
body.oa-lite-theme-dark .z-popup .bg-card,
body.oa-lite-theme-dark .z-popup .text-popover-foreground,
body.oa-lite-theme-dark .z-popup .text-foreground,
body.oa-lite-theme-dark .z-popup .text-card-foreground,
body.oa-lite-theme-dark .z-popup .text-muted-foreground,
body.oa-lite-theme-dark [role='dialog'] .bg-popover,
body.oa-lite-theme-dark [role='dialog'] .bg-background,
body.oa-lite-theme-dark [role='dialog'] .bg-card,
body.oa-lite-theme-dark [role='menu'] .bg-popover,
body.oa-lite-theme-dark [role='menu'] .bg-background,
body.oa-lite-theme-dark [role='menu'] .bg-card {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .z-popup .text-muted-foreground,
body.oa-lite-theme-light [role='dialog'] .text-muted-foreground,
body.oa-lite-theme-light [role='menu'] .text-muted-foreground,
body.oa-lite-theme-dark .z-popup .text-muted-foreground,
body.oa-lite-theme-dark [role='dialog'] .text-muted-foreground,
body.oa-lite-theme-dark [role='menu'] .text-muted-foreground {
  color: var(--oa-ink-soft) !important;
}

body.oa-lite-theme-light .z-popup .border-border,
body.oa-lite-theme-light [role='dialog'] .border-border,
body.oa-lite-theme-light [role='menu'] .border-border,
body.oa-lite-theme-dark .z-popup .border-border,
body.oa-lite-theme-dark [role='dialog'] .border-border,
body.oa-lite-theme-dark [role='menu'] .border-border {
  border-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme-light .z-popup [data-highlighted],
body.oa-lite-theme-light .z-popup .hover\:bg-accent:hover,
body.oa-lite-theme-light [role='menu'] [data-highlighted],
body.oa-lite-theme-light [role='menu'] .hover\:bg-accent:hover,
body.oa-lite-theme-light [role='dialog'] .hover\:bg-accent:hover,
body.oa-lite-theme-dark .z-popup [data-highlighted],
body.oa-lite-theme-dark .z-popup .hover\:bg-accent:hover,
body.oa-lite-theme-dark [role='menu'] [data-highlighted],
body.oa-lite-theme-dark [role='menu'] .hover\:bg-accent:hover,
body.oa-lite-theme-dark [role='dialog'] .hover\:bg-accent:hover {
  background: var(--oa-shell-surface-muted) !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .z-popup button,
body.oa-lite-theme-light .z-popup svg,
body.oa-lite-theme-light .z-popup .anticon,
body.oa-lite-theme-light [role='dialog'] button,
body.oa-lite-theme-light [role='dialog'] svg,
body.oa-lite-theme-light [role='menu'] button,
body.oa-lite-theme-light [role='menu'] svg,
body.oa-lite-theme-dark .z-popup button,
body.oa-lite-theme-dark .z-popup svg,
body.oa-lite-theme-dark .z-popup .anticon,
body.oa-lite-theme-dark [role='dialog'] button,
body.oa-lite-theme-dark [role='dialog'] svg,
body.oa-lite-theme-dark [role='menu'] button,
body.oa-lite-theme-dark [role='menu'] svg {
  color: var(--oa-ink) !important;
}
</style>
