<script lang="ts" setup>
import type { BpmCategoryApi } from '#/api/bpm/category';
import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { BpmTaskApi } from '#/api/bpm/task';

import {
  computed,
  defineAsyncComponent,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute } from 'vue-router';

import { BpmModelFormType, BpmProcessInstanceStatus } from '@vben/constants';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';
import { useUserStore } from '@vben/stores';
import { formatDateTime } from '@vben/utils';
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
type ManagementSection = 'bpm' | 'system';
type WorkbenchNavKey = MainTab | ManagementSection;
type DateRangeValue = [string, string];
interface WorkbenchSidebarItem {
  children?: readonly { key: string; label: string }[];
  count?: number;
  icon: string;
  key: WorkbenchNavKey;
  label: string;
}
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

interface OaLiteRouteDetail {
  request: OaLiteDetailRequest;
  section: OaLiteDetailSection;
}

const MANAGEMENT_COMPONENTS = {
  bpm: {
    category: defineAsyncComponent(() => import('#/views/bpm/category/index.vue')),
    definition: defineAsyncComponent(() => import('#/views/bpm/model/definition/index.vue')),
    expression: defineAsyncComponent(
      () => import('#/views/bpm/processExpression/index.vue'),
    ),
    form: defineAsyncComponent(() => import('#/views/bpm/form/index.vue')),
    formEditor: defineAsyncComponent(
      () => import('#/views/bpm/form/designer/index.vue'),
    ),
    group: defineAsyncComponent(() => import('#/views/bpm/group/index.vue')),
    listener: defineAsyncComponent(
      () => import('#/views/bpm/processListener/index.vue'),
    ),
    model: defineAsyncComponent(() => import('#/views/bpm/model/index.vue')),
    modelEditor: defineAsyncComponent(
      () => import('#/views/bpm/model/form/index.vue'),
    ),
    process: defineAsyncComponent(
      () => import('#/views/bpm/processInstance/manager/index.vue'),
    ),
    report: defineAsyncComponent(
      () => import('#/views/bpm/processInstance/report/index.vue'),
    ),
    template: defineAsyncComponent(
      () => import('#/views/bpm/approvalTemplate/index.vue'),
    ),
  },
  system: {
    dept: defineAsyncComponent(() => import('#/views/system/dept/index.vue')),
    notice: defineAsyncComponent(() => import('#/views/system/notice/index.vue')),
    post: defineAsyncComponent(() => import('#/views/system/post/index.vue')),
    role: defineAsyncComponent(() => import('#/views/system/role/index.vue')),
    user: defineAsyncComponent(() => import('#/views/system/user/index.vue')),
  },
} as const;

const MANAGEMENT_NAV_ITEMS = {
  bpm: [
    { key: 'category', label: '流程分类' },
    { key: 'form', label: '流程表单' },
    { key: 'template', label: '审批模板管理' },
    { key: 'model', label: '流程模型' },
    { key: 'definition', label: '流程定义' },
    { key: 'process', label: '流程实例' },
    { key: 'group', label: '用户组' },
  ],
  system: [
    { key: 'user', label: '用户管理' },
    { key: 'role', label: '角色管理' },
    { key: 'dept', label: '部门管理' },
    { key: 'post', label: '岗位管理' },
    { key: 'notice', label: '通知公告' },
  ],
} as const;

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
const OA_LITE_VIEW_QUERY_KEY = 'view';
const OA_LITE_CREATE_VIEW = 'create';
const OA_LITE_CENTER_VIEW = 'center';
const OA_LITE_DETAIL_SECTION_QUERY_KEY = 'detailSection';
const OA_LITE_DETAIL_PROCESS_QUERY_KEY = 'detailProcessInstanceId';
const OA_LITE_DETAIL_TASK_QUERY_KEY = 'detailTaskId';
const OA_LITE_DETAIL_ACTIVITY_QUERY_KEY = 'detailActivityId';
const OA_LITE_TASK_ASSIGNED_MESSAGE_TYPE = 'task-assigned';
const OA_LITE_TASK_ASSIGNED_TOAST_KEY = 'oa-lite-task-assigned';
const accessStore = useAccessStore();
const userStore = useUserStore();
const route = useRoute();

const initializing = ref(true);
const activeTab = ref<MainTab>('create');
const lastCenterTab = ref<ListTab>('pending');
const expandedManagementSection = ref<ManagementSection | null>(null);

const managementSection = computed<ManagementSection | null>(() => {
  const value = route.query.manage;
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return normalizedValue === 'bpm' || normalizedValue === 'system'
    ? normalizedValue
    : null;
});
const managementPage = computed(() => {
  const value = route.query.page;
  return Array.isArray(value) ? value[0] : value;
});
const bpmManagementView = computed(() => {
  const value = route.query.bpmView;
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return normalizedValue === 'form-editor' || normalizedValue === 'model-editor'
    ? normalizedValue
    : null;
});
const managementComponentProps = computed(() => {
  if (
    managementSection.value !== 'bpm' ||
    managementPage.value !== 'form' ||
    bpmManagementView.value !== 'form-editor'
  ) {
    return { type: 'create' as const };
  }
  const readQueryValue = (key: string): string | undefined => {
    const value = route.query[key];
    const normalizedValue = Array.isArray(value) ? value[0] : value;
    return typeof normalizedValue === 'string' ? normalizedValue : undefined;
  };
  const type = readQueryValue('type');
  const formType: 'copy' | 'create' | 'edit' =
    type === 'copy' || type === 'edit' || type === 'create' ? type : 'create';
  return {
    copyId: readQueryValue('copyId'),
    id: readQueryValue('id'),
    type: formType,
  };
});
const managementComponentKey = computed(() => {
  const readQueryValue = (key: string) => {
    const value = route.query[key];
    return Array.isArray(value) ? value[0] : value;
  };
  return [
    managementSection.value || '',
    managementPage.value || '',
    bpmManagementView.value || '',
    readQueryValue('id') || '',
    readQueryValue('copyId') || '',
    readQueryValue('modelAction') || '',
    readQueryValue('modelId') || '',
    readQueryValue('type') || '',
  ].join(':');
});
const isCurrentUserAdmin = computed(() => isAdminUser(userStore.userRoles));
const currentManagementComponent = computed(() => {
  if (
    !isCurrentUserAdmin.value ||
    !managementSection.value ||
    !managementPage.value
  ) {
    return null;
  }
  const components = MANAGEMENT_COMPONENTS[managementSection.value] as Record<
    string,
    unknown
  >;
  if (managementSection.value === 'bpm' && bpmManagementView.value) {
    return bpmManagementView.value === 'form-editor'
      ? components.formEditor
      : components.modelEditor;
  }
  return components[managementPage.value] || null;
});
const isManagementView = computed(() => Boolean(currentManagementComponent.value));

watch(
  managementSection,
  (section) => {
    expandedManagementSection.value = section;
  },
  { immediate: true },
);
const selectedItem = ref<DetailPayload>(null);
const routeDetail = ref<OaLiteRouteDetail | null>(null);
const filtersExpanded = ref(false);
const categories = ref<BpmCategoryApi.Category[]>([]);
const oaTemplateDefinitions = ref<BpmProcessDefinitionApi.ProcessDefinition[]>([]);
const todoItems = ref<BpmTaskApi.Task[]>([]);
const doneItems = ref<BpmTaskApi.Task[]>([]);
const initiatedItems = ref<BpmProcessInstanceApi.ProcessInstance[]>([]);
const managerProcessItems = ref<BpmProcessInstanceApi.ProcessInstance[]>([]);
const copiedItems = ref<BpmProcessInstanceApi.ProcessInstanceCopyRespVO[]>([]);
const displayNumberMap = new Map<string, string>();
const displayNumberCounters = new Map<string, number>();
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

function buildWorkbenchQuery(view: string, extra: Record<string, string> = {}) {
  const query = { ...buildApprovalEntryQuery() } as Record<string, any>;
  delete query.manage;
  delete query.page;
  delete query[OA_LITE_DETAIL_SECTION_QUERY_KEY];
  delete query[OA_LITE_DETAIL_PROCESS_QUERY_KEY];
  delete query[OA_LITE_DETAIL_TASK_QUERY_KEY];
  delete query[OA_LITE_DETAIL_ACTIVITY_QUERY_KEY];
  // 深层 BPM 编辑器只能在对应页面中保留。切换工作台导航时必须清理，
  // 否则“流程模型”等菜单会继续渲染上一个表单设计器。
  delete query.bpmView;
  delete query.copyId;
  delete query.id;
  delete query.modelAction;
  delete query.modelId;
  delete query.type;
  // 这两个参数只用于可道云首次进入发起页，不能带到工作台其它视图，
  // 否则路由监听会把待办、已办等页面再次强制切回发起审批。
  delete query.forceCreate;
  delete query.autoStart;
  return {
    ...query,
    view,
    ...extra,
  };
}

function shouldForceCreateMode() {
  return isForceCreateEntry(route.query) || readOaLiteView() === OA_LITE_CREATE_VIEW;
}

function readOaLiteView() {
  const view = route.query[OA_LITE_VIEW_QUERY_KEY];
  const normalizedView = Array.isArray(view) ? view[0] : view;
  return normalizedView === OA_LITE_CREATE_VIEW || normalizedView === OA_LITE_CENTER_VIEW
    ? normalizedView
    : null;
}

function readRouteQueryValue(key: string) {
  const value = route.query[key];
  return Array.isArray(value) ? value[0] : value;
}

function resolveRouteDetailFromRoute(): null | OaLiteRouteDetail {
  const processInstanceId = readRouteQueryValue(OA_LITE_DETAIL_PROCESS_QUERY_KEY);
  if (!processInstanceId) {
    return null;
  }
  const requestedSection = readRouteQueryValue(OA_LITE_DETAIL_SECTION_QUERY_KEY);
  const taskId = readRouteQueryValue(OA_LITE_DETAIL_TASK_QUERY_KEY);
  const activityId = readRouteQueryValue(OA_LITE_DETAIL_ACTIVITY_QUERY_KEY);
  // 管理端“流程实例”详情必须保留 manager，否则会被降级到“我发起的”。
  const section: OaLiteDetailSection =
    requestedSection === 'pending' ||
    requestedSection === 'processed' ||
    requestedSection === 'copied' ||
    requestedSection === 'initiated' ||
    requestedSection === 'manager'
      ? requestedSection
      : taskId
        ? 'pending'
        : 'initiated';
  return {
    request: {
      activityId: activityId || undefined,
      processInstanceId: String(processInstanceId),
      taskId: taskId || undefined,
    },
    section,
  };
}

function syncRouteDetailFromRoute() {
  const nextDetail = resolveRouteDetailFromRoute();
  routeDetail.value = nextDetail;
  if (nextDetail) {
    if (nextDetail.section !== 'manager') {
      activeTab.value = nextDetail.section;
      lastCenterTab.value = nextDetail.section;
    }
    selectedItem.value = null;
  }
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
    const isStandaloneProjectTemplate =
      (definition.key && ['oa_project', 'oa_staffing'].includes(definition.key)) ||
      definition.category === 'project' ||
      definition.categoryName === '项目管理';
    if (isStandaloneProjectTemplate) {
      return;
    }
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

const workbenchSidebarItems = computed<WorkbenchSidebarItem[]>(() => [
  {
    count: undefined,
    icon: 'solar:pen-new-square-outline',
    key: 'create' as const,
    label: '发起审批',
  },
  ...dashboardNavItems.value,
  {
    count: undefined,
    icon: 'solar:checklist-outline',
    key: 'bpm' as const,
    label: '流程管理',
    children: MANAGEMENT_NAV_ITEMS.bpm,
  },
  {
    count: undefined,
    icon: 'solar:settings-outline',
    key: 'system' as const,
    label: '系统管理',
    children: MANAGEMENT_NAV_ITEMS.system,
  },
].filter((item) =>
  isCurrentUserAdmin.value || (item.key !== 'bpm' && item.key !== 'system'),
));

const activeManagementSection = computed(() => managementSection.value);

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
  if (routeDetail.value) {
    return routeDetail.value.section;
  }
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
  if (routeDetail.value) {
    return routeDetail.value.request;
  }
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
const isDetailOpen = computed(
  () => Boolean(selectedItem.value) || Boolean(routeDetail.value),
);
const isCenterMode = computed(
  () => activeTab.value !== 'create' || isManagementView.value,
);

const currentListTitle = computed(() => {
  if (routeDetail.value?.section === 'manager') {
    return '流程实例';
  }
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
  selectedItem.value = matchedItem || null;
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

function getProcessTypeLabel(item: DetailPayload) {
  if (!item) {
    return '审批';
  }
  if (isTaskItem(item)) {
    return (
      item.processInstance?.categoryName ||
      item.processInstance?.category ||
      item.processInstance?.name ||
      item.name ||
      '审批'
    );
  }
  if (isCopiedItem(item)) {
    return item.processInstanceName || '审批';
  }
  return item.categoryName || item.category || item.name || '审批';
}

function getProcessTypePrefix(label: string) {
  if (/报销/.test(label)) return 'BXSQ';
  if (/加班/.test(label)) return 'JBSQ';
  if (/请假|销假/.test(label)) return /销假/.test(label) ? 'XJSQ' : 'QJSQ';
  if (/出差/.test(label)) return 'CCSQ';
  if (/用章|印章/.test(label)) return 'YZSQ';
  if (/补卡/.test(label)) return 'BKSQ';
  if (/外出|外勤/.test(label)) return 'WCSQ';
  if (/公文|文件/.test(label)) return 'GWSQ';
  if (/项目/.test(label)) return 'XMSQ';
  return 'SQSQ';
}

function getProcessStartDate(item: DetailPayload) {
  if (!item) return new Date();
  if (isTaskItem(item)) {
    return item.processInstance?.startTime || item.processInstance?.createTime;
  }
  if (isCopiedItem(item)) {
    return item.processInstanceStartTime || item.createTime;
  }
  return item.startTime || item.createTime;
}

function getDisplayNumberKey(item: DetailPayload) {
  if (!item) {
    return '';
  }
  if (isTaskItem(item)) {
    return `process:${item.processInstanceId || item.processInstance?.id || item.id}`;
  }
  if (isCopiedItem(item)) {
    return `process:${item.processInstanceId || item.id}`;
  }
  return `process:${item.id}`;
}

function buildDisplayNumber(item: DetailPayload) {
  const existingNumber = isTaskItem(item)
    ? item.processInstance?.businessKey
    : isCopiedItem(item)
      ? undefined
      : item?.businessKey;
  if (existingNumber && !/^\d+$/.test(String(existingNumber))) {
    return String(existingNumber);
  }

  const label = getProcessTypeLabel(item);
  const prefix = getProcessTypePrefix(label);
  const startDate = new Date(getProcessStartDate(item) as any);
  const date = Number.isNaN(startDate.getTime())
    ? new Date()
    : startDate;
  const dateText = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('');
  const counterKey = `${prefix}-${dateText}`;
  const nextNumber = (displayNumberCounters.get(counterKey) || 0) + 1;
  displayNumberCounters.set(counterKey, nextNumber);
  return `${prefix}-${dateText}-${String(nextNumber).padStart(2, '0')}`;
}

function getListNumber(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  const key = getDisplayNumberKey(item);
  const cachedNumber = displayNumberMap.get(key);
  if (cachedNumber) {
    return cachedNumber;
  }
  const displayNumber = buildDisplayNumber(item);
  displayNumberMap.set(key, displayNumber);
  return displayNumber;
}

function getListType(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return item.processInstance?.categoryName || item.processInstance?.category || '-';
  }
  if (isCopiedItem(item)) {
    return item.processInstanceName || '-';
  }
  return item.categoryName || item.category || '-';
}

function getListProcessName(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return item.processInstance?.name || item.name || '-';
  }
  if (isCopiedItem(item)) {
    return item.processInstanceName || '-';
  }
  return item.name || '-';
}

function getListStarter(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return item.processInstance?.startUser?.nickname || '-';
  }
  if (isCopiedItem(item)) {
    return item.startUser?.nickname || '-';
  }
  return item.startUser?.nickname || '-';
}

function getListStage(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return item.name || '-';
  }
  if (isCopiedItem(item)) {
    return item.activityName || '-';
  }
  return item.tasks?.[0]?.name || getProcessStatusText(item.status);
}

function getListStartTime(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return formatDateTime(item.processInstance?.startTime || item.processInstance?.createTime);
  }
  if (isCopiedItem(item)) {
    return formatDateTime(item.processInstanceStartTime || item.createTime);
  }
  return formatDateTime(item.startTime || item.createTime);
}

function getListEndTime(item: DetailPayload) {
  if (!item) {
    return '-';
  }
  if (isTaskItem(item)) {
    return formatDateTime(item.processInstance?.endTime || item.endTime);
  }
  if (isCopiedItem(item)) {
    return '-';
  }
  return formatDateTime(item.endTime);
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

async function openTab(tab: MainTab) {
  routeDetail.value = null;
  selectedItem.value = null;
  if (tab !== 'create') {
    lastCenterTab.value = tab;
  }
  activeTab.value = tab;
  await router.replace({
    path: OA_LITE_CENTER_PATH,
    query: buildWorkbenchQuery(
      tab === 'create' ? OA_LITE_CREATE_VIEW : OA_LITE_CENTER_VIEW,
    ),
  });
}

async function handleWorkbenchSidebarSelect(
  key: WorkbenchNavKey,
) {
  if (key === 'bpm' || key === 'system') {
    if (!isCurrentUserAdmin.value) {
      return;
    }
    expandedManagementSection.value =
      expandedManagementSection.value === key ? null : key;
    return;
  }
  await openTab(key);
}

async function handleManagementSelect(
  section: ManagementSection,
  page: string,
) {
  if (!isCurrentUserAdmin.value) {
    return;
  }
  expandedManagementSection.value = section;
  await router.replace({
    path: OA_LITE_CENTER_PATH,
    query: buildWorkbenchQuery(OA_LITE_CENTER_VIEW, {
      manage: section,
      page,
    }),
  });
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

function openDetail(item: DetailPayload) {
  routeDetail.value = null;
  selectedItem.value = item;
}

async function closeDetail() {
  routeDetail.value = null;
  selectedItem.value = null;
  const nextQuery = { ...route.query } as Record<string, any>;
  delete nextQuery[OA_LITE_DETAIL_SECTION_QUERY_KEY];
  delete nextQuery[OA_LITE_DETAIL_PROCESS_QUERY_KEY];
  delete nextQuery[OA_LITE_DETAIL_TASK_QUERY_KEY];
  delete nextQuery[OA_LITE_DETAIL_ACTIVITY_QUERY_KEY];
  await router.replace({ path: OA_LITE_CENTER_PATH, query: nextQuery });
}

async function handleDetailRefresh() {
  await refreshAllTabs();
  if (activeTab.value !== 'create' && !routeDetail.value) {
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
  routeDetail.value = null;
  activeTab.value = 'pending';
  lastCenterTab.value = 'pending';
  if (route.path !== OA_LITE_CENTER_PATH || readOaLiteView() !== OA_LITE_CENTER_VIEW) {
    await router.replace({
      path: OA_LITE_CENTER_PATH,
      query: {
        ...buildApprovalEntryQuery(),
        [OA_LITE_VIEW_QUERY_KEY]: OA_LITE_CENTER_VIEW,
      },
    });
  } else if (
    OA_LITE_DETAIL_PROCESS_QUERY_KEY in route.query ||
    OA_LITE_DETAIL_TASK_QUERY_KEY in route.query ||
    OA_LITE_DETAIL_ACTIVITY_QUERY_KEY in route.query
  ) {
    await router.replace({
      path: OA_LITE_CENTER_PATH,
      query: buildWorkbenchQuery(OA_LITE_CENTER_VIEW),
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
  () => [route.path, readOaLiteView()],
  ([path, view]) => {
    if (path === OA_LITE_CREATE_PATH || view === OA_LITE_CREATE_VIEW || shouldForceCreateMode()) {
      activeTab.value = 'create';
      return;
    }
    if (path === OA_LITE_CENTER_PATH && view !== OA_LITE_CREATE_VIEW && activeTab.value === 'create') {
      activeTab.value = lastCenterTab.value;
    }
  },
  { immediate: true },
);

watch(
  () => [
    readRouteQueryValue(OA_LITE_DETAIL_SECTION_QUERY_KEY),
    readRouteQueryValue(OA_LITE_DETAIL_PROCESS_QUERY_KEY),
    readRouteQueryValue(OA_LITE_DETAIL_TASK_QUERY_KEY),
    readRouteQueryValue(OA_LITE_DETAIL_ACTIVITY_QUERY_KEY),
  ],
  () => {
    syncRouteDetailFromRoute();
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
          <div class="oa-lite-workbench-layout">
            <aside class="oa-lite-workbench-sidebar">
              <template v-for="item in workbenchSidebarItems" :key="item.key">
                <button
                  class="oa-lite-center-nav-item"
                  :class="{
                    active:
                      item.key === 'create'
                        ? activeTab === 'create' && !isManagementView
                        : item.key === activeTab || activeManagementSection === item.key,
                    'has-children': Boolean(item.children),
                  }"
                  @click="handleWorkbenchSidebarSelect(item.key)"
                >
                  <span class="oa-lite-center-nav-main">
                    <span class="oa-lite-center-nav-icon">
                      <IconifyIcon :icon="item.icon" />
                    </span>
                    <span class="oa-lite-center-nav-text">{{ item.label }}</span>
                  </span>
                  <span class="oa-lite-center-nav-trailing">
                    <Tag v-if="item.count !== undefined" class="oa-lite-center-nav-count">
                      {{ item.count }}
                    </Tag>
                    <IconifyIcon
                      v-if="item.children"
                      :icon="
                        expandedManagementSection === item.key
                          ? 'solar:alt-arrow-up-outline'
                          : 'solar:alt-arrow-down-outline'
                      "
                      class="oa-lite-center-nav-chevron"
                    />
                  </span>
                </button>
                <div
                  v-if="item.children && expandedManagementSection === item.key"
                  class="oa-lite-center-nav-children"
                >
                  <button
                    v-for="child in item.children"
                    :key="child.key"
                    class="oa-lite-center-nav-child"
                    :class="{
                      active:
                        activeManagementSection === item.key && managementPage === child.key,
                    }"
                    @click.stop="handleManagementSelect(item.key as ManagementSection, child.key)"
                  >
                    {{ child.label }}
                  </button>
                </div>
              </template>
            </aside>

            <div class="oa-lite-workbench-content">
          <div class="oa-lite-home-shell" :class="{ 'is-center-mode': isCenterMode }">
            <template v-if="isManagementView && !isDetailOpen">
              <div class="oa-lite-management-view">
                <!-- 编辑器与管理列表不能复用同一个异步动态组件出口。
                     否则切换菜单后，已加载的设计器可能保留在页面上。 -->
                <component
                  v-if="bpmManagementView === 'form-editor'"
                  :is="MANAGEMENT_COMPONENTS.bpm.formEditor"
                  :key="managementComponentKey"
                  v-bind="managementComponentProps"
                />
                <component
                  v-else-if="bpmManagementView === 'model-editor'"
                  :is="MANAGEMENT_COMPONENTS.bpm.modelEditor"
                  :key="managementComponentKey"
                />
                <component
                  v-else
                  :is="currentManagementComponent"
                  :key="managementComponentKey"
                />
              </div>
            </template>

            <template v-else-if="activeTab === 'create' && !isDetailOpen">
              <section class="oa-lite-section-header">
                <div>
                  <div class="oa-lite-section-title">发起审批</div>
                </div>
              </section>

              <section class="oa-lite-create-shell">
                <div v-if="createCategorySections.length > 0" class="oa-lite-create-sections">
                  <section
                    v-for="section in createCategorySections"
                    :key="section.code"
                    class="oa-lite-template-section"
                  >
                    <div class="oa-lite-template-section-head">
                      <span class="oa-lite-template-section-title">{{ section.name }}</span>
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
                <div
                  class="oa-lite-center-content"
                  :class="{ 'is-detail-mode': isDetailOpen }"
                >
                  <div v-if="!isDetailOpen" class="oa-lite-list-panel">
                    <div class="oa-lite-list-headline">
                      <span class="oa-lite-list-total">
                        {{ currentPageState?.total || currentList.length }} 条记录
                      </span>
                      <div class="oa-lite-list-toolbar">
                        <Button type="link" @click="resetCurrentFilter">重置筛选</Button>
                      </div>
                    </div>

                    <div class="oa-lite-filter-shell">
                      <div class="oa-lite-filter-primary-row">
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
                        <button
                          class="oa-lite-filter-expand-button"
                          :class="{ active: filtersExpanded }"
                          type="button"
                          :aria-expanded="filtersExpanded"
                          aria-label="展开筛选条件"
                          @click="filtersExpanded = !filtersExpanded"
                        >
                          <IconifyIcon icon="solar:filter-outline" />
                          <span>筛选</span>
                          <IconifyIcon
                            icon="solar:alt-arrow-down-outline"
                            class="oa-lite-filter-expand-arrow"
                          />
                        </button>
                      </div>

                      <div v-if="filtersExpanded" class="oa-lite-filter-expanded">
                        <div class="oa-lite-filters">
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
                    </div>

                    <div class="oa-lite-list-scroll-region">
                      <Spin :spinning="currentListLoading" class="oa-lite-list-spin">
                        <div v-if="currentList.length > 0" class="oa-lite-list-scroll-body">
                          <div class="oa-lite-approval-table">
                            <div class="oa-lite-approval-table-row oa-lite-approval-table-head">
                              <span>编号</span>
                              <span>流程名称</span>
                              <span>类型</span>
                              <span>发起人</span>
                              <span>当前阶段</span>
                              <span>发起时间</span>
                              <span>结束时间</span>
                              <span>操作</span>
                            </div>
                            <button
                              v-for="item in currentList"
                              :key="getItemIdentity(item)"
                              class="oa-lite-approval-table-row oa-lite-approval-table-item"
                              :class="{ active: selectedItem === item }"
                              @click="openDetail(item)"
                            >
                              <span>{{ getListNumber(item) }}</span>
                              <span>{{ getListProcessName(item) }}</span>
                              <span>{{ getListType(item) }}</span>
                              <span>{{ getListStarter(item) }}</span>
                              <span>{{ getListStage(item) }}</span>
                              <span>{{ getListStartTime(item) }}</span>
                              <span>{{ getListEndTime(item) }}</span>
                              <span class="oa-lite-approval-table-action">详情</span>
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

                  <div v-else class="oa-lite-detail-panel oa-lite-detail-panel--full">
                    <div class="oa-lite-detail-header">
                      <Button type="link" class="oa-lite-detail-back" @click="closeDetail">
                        <IconifyIcon icon="solar:arrow-left-outline" />
                        返回列表
                      </Button>
                      <span class="oa-lite-detail-title">{{ currentListTitle }}详情</span>
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
                      <div class="oa-lite-detail-empty-copy">
                        <IconifyIcon icon="solar:checklist-minimalistic-outline" />
                        <strong>请选择一条{{ currentListTitle }}</strong>
                        <span>点击左侧列表后查看审批表单和完整审批链</span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
            </template>
          </div>
            </div>
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

.oa-lite-page:has(.oa-lite-main.is-center-mode) {
  height: 100%;
  min-height: 0;
  overflow: hidden;
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

.oa-lite-main.oa-lite-main-embedded {
  width: 100%;
  padding: 6px 0 32px !important;
}

.oa-lite-main.is-center-mode {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding-bottom: 0;
  padding-right: 0;
  padding-left: 0;
}

.oa-lite-main.is-center-mode :deep(.ant-spin-nested-loading),
.oa-lite-main.is-center-mode :deep(.ant-spin-container) {
  height: 100%;
  min-height: 0;
}

.oa-lite-main.is-center-mode :deep(.ant-spin-container) {
  display: flex;
  flex-direction: column;
}

.oa-lite-home-shell {
  width: 100%;
  max-width: none !important;
  margin: 0 !important;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.oa-lite-workbench-layout {
  width: 100%;
  display: grid;
  grid-template-columns: 176px minmax(0, 1fr);
  gap: 16px;
  min-width: 0;
  min-height: 0;
}

.oa-lite-workbench-layout:has(.oa-lite-home-shell.is-center-mode) {
  height: 100%;
}

.oa-lite-workbench-sidebar {
  min-width: 0;
  padding: 16px 0 18px;
}

.oa-lite-workbench-content {
  min-width: 0;
  min-height: 0;
}

.oa-lite-management-view {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 16px 0 18px;
}

.oa-lite-home-shell.is-center-mode {
  height: 100%;
  min-height: 0;
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
  min-height: 36px;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.oa-lite-center-shell {
  --oa-lite-center-panel-height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
  align-items: stretch;
  height: 100%;
  min-height: 0;
  min-width: 0;
  padding: 16px 0 18px;
  background: var(--oa-shell-bg);
}

.oa-lite-center-nav {
  padding: 4px 0;
  border-right: 0;
  border-radius: 0;
  background: transparent;
}

.oa-lite-center-nav-item {
  width: 100%;
  min-height: 44px;
  margin: 0 0 4px;
  border: none;
  border-radius: 8px;
  background: transparent;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--oa-ink-soft);
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
  position: relative;
}

.oa-lite-center-nav-item:hover {
  color: var(--oa-ink);
  background: color-mix(in srgb, var(--oa-shell-surface) 74%, transparent);
}

.oa-lite-center-nav-item.active {
  color: var(--oa-accent);
  background: var(--oa-shell-surface);
  box-shadow: 0 1px 3px rgb(15 23 42 / 6%);
}

.oa-lite-center-nav-item.active::before {
  display: none;
}

.oa-lite-center-nav-item.has-children {
  margin-bottom: 2px;
}

.oa-lite-center-nav-trailing {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--oa-ink-faint);
}

.oa-lite-center-nav-chevron {
  font-size: 14px;
}

.oa-lite-center-nav-children {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0 0 8px 28px;
  padding-left: 12px;
  border-left: 1px solid var(--oa-shell-border);
}

.oa-lite-center-nav-child {
  min-height: 32px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--oa-ink-soft);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.oa-lite-center-nav-child:hover,
.oa-lite-center-nav-child.active {
  background: var(--oa-shell-surface);
  color: var(--oa-accent);
}

.oa-lite-center-nav-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.oa-lite-center-nav-icon {
  font-size: 18px;
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
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  height: 100%;
  min-height: 0;
  align-items: stretch;
  min-width: 0;
  overflow: hidden;
}

.oa-lite-list-panel,
.oa-lite-detail-panel {
  height: 100%;
  background: var(--oa-shell-surface);
  border: 1px solid var(--oa-shell-border);
  border-radius: 12px;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.oa-lite-list-panel {
  padding: 0 12px 12px;
}

.oa-lite-detail-panel {
  padding: 0;
}

.oa-lite-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  min-height: 52px;
  padding: 0 18px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-lite-detail-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding-inline: 0;
}

.oa-lite-detail-title {
  color: var(--oa-ink);
  font-size: 15px;
  font-weight: 600;
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
  font-size: 16px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-list-headline {
  display: flex;
  min-height: 40px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 4px;
  border-bottom: 0;
}

.oa-lite-list-total {
  color: var(--oa-ink);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.oa-lite-list-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.oa-lite-list-toolbar :deep(.ant-btn-link) {
  height: 28px;
  padding: 0 4px;
  color: var(--oa-ink-soft);
  font-size: 12px;
}

.oa-lite-filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.oa-lite-filter-primary-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.oa-lite-filter-primary-row > :deep(.ant-input-affix-wrapper) {
  flex: 1;
  min-width: 0;
}

.oa-lite-filter-expand-button {
  display: inline-flex;
  height: 32px;
  flex: none;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  border: 1px solid var(--oa-shell-border);
  border-radius: 4px;
  background: var(--oa-shell-surface);
  color: var(--oa-ink-soft);
  cursor: pointer;
  font-size: 12px;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.oa-lite-filter-expand-button:hover,
.oa-lite-filter-expand-button.active {
  border-color: color-mix(in srgb, var(--oa-accent) 52%, var(--oa-shell-border));
  background: color-mix(in srgb, var(--oa-accent) 7%, var(--oa-shell-surface));
  color: var(--oa-accent);
}

.oa-lite-filter-expand-arrow {
  margin-left: 1px;
  font-size: 12px;
  transition: transform 0.18s ease;
}

.oa-lite-filter-expand-button.active .oa-lite-filter-expand-arrow {
  transform: rotate(180deg);
}

.oa-lite-filter-expanded {
  padding-top: 8px;
}

.oa-lite-filter-range {
  grid-column: 1 / -1;
}

.oa-lite-filter-control,
.oa-lite-filter-range {
  width: 100%;
}

.oa-lite-filter-shell {
  margin-bottom: 8px;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
}

.oa-lite-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 10px;
  flex-shrink: 0;
}

.oa-lite-filter-actions :deep(.ant-btn) {
  height: 30px;
  padding: 0 16px;
  border-radius: 4px;
  font-size: 13px;
}

.oa-lite-list-scroll-region {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
  padding-right: 3px;
}

.oa-lite-list-spin {
  display: flex;
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
}

.oa-lite-list-spin :deep(.ant-spin-nested-loading),
.oa-lite-list-spin :deep(.ant-spin-container) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  width: 100%;
  overflow: visible;
}

.oa-lite-list-scroll-body {
  display: flex;
  flex: 1;
  min-height: 0;
  min-width: 0;
  width: 100%;
  overflow: visible;
}

.oa-lite-approval-table {
  width: 100%;
  min-width: 1120px;
  overflow: hidden;
  border: 1px solid var(--oa-shell-border);
  border-radius: 10px;
  background: var(--oa-shell-surface);
}

.oa-lite-approval-table-row {
  display: grid;
  grid-template-columns: minmax(150px, 1.2fr) minmax(180px, 1.4fr) minmax(120px, 1fr) minmax(100px, .8fr) minmax(110px, .9fr) minmax(150px, 1fr) minmax(150px, 1fr) 64px;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  text-align: left;
}

.oa-lite-approval-table-head {
  color: var(--oa-ink-soft);
  font-size: 12px;
  font-weight: 600;
  background: var(--oa-shell-surface-muted);
}

.oa-lite-approval-table-item {
  border: 0;
  border-top: 1px solid var(--oa-shell-border);
  color: var(--oa-ink);
  cursor: pointer;
  font-size: 13px;
  background: transparent;
  transition: background-color .2s ease;
}

.oa-lite-approval-table-item:hover,
.oa-lite-approval-table-item.active {
  background: color-mix(in srgb, var(--oa-accent) 8%, transparent);
}

.oa-lite-approval-table-item > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-lite-approval-table-action {
  color: var(--oa-accent);
  font-weight: 600;
}

.oa-lite-list {
  display: flex;
  flex-direction: column;
  flex: none;
  min-height: 100%;
  min-width: 0;
  width: 100%;
  overflow: visible;
  gap: 8px;
  padding: 2px 2px 8px;
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
  min-height: 92px;
  margin: 0;
  border: 1px solid var(--oa-shell-border);
  background: var(--oa-shell-surface);
  border-radius: 10px;
  text-align: left;
  padding: 13px 14px;
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
  border-bottom-color: var(--oa-shell-border);
}

.oa-lite-list-item:hover {
  border-color: color-mix(in srgb, var(--oa-accent) 32%, var(--oa-shell-border));
  background: color-mix(in srgb, var(--oa-accent) 3%, var(--oa-shell-surface));
}

.oa-lite-list-item.active {
  border: 2px solid var(--oa-accent);
  padding: 12px 13px;
  background: color-mix(in srgb, var(--oa-accent) 5%, var(--oa-shell-surface));
}

.oa-lite-list-item.active::before {
  display: none;
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
  font-size: 14px;
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
  font-weight: 400;
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
  font-size: 12px;
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
  border-bottom: 0;
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
  margin-top: 10px;
  padding: 10px 4px 0;
  border-top: 1px solid var(--oa-shell-border);
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.oa-lite-detail-scroll-region {
  flex: 1;
  min-height: 0;
  overflow-y: hidden;
  overflow-x: hidden;
  padding-right: 0;
}

.oa-lite-detail-empty {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.oa-lite-detail-empty-copy {
  display: flex;
  max-width: 280px;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--oa-ink-soft);
  text-align: center;
}

.oa-lite-detail-empty-copy :deep(svg) {
  margin-bottom: 4px;
  color: var(--oa-accent);
  font-size: 34px;
}

.oa-lite-detail-empty-copy strong {
  color: var(--oa-ink);
  font-size: 15px;
  font-weight: 600;
}

.oa-lite-detail-empty-copy span {
  font-size: 12px;
  line-height: 1.6;
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

  .oa-lite-workbench-layout,
  .oa-lite-center-shell,
  .oa-lite-center-content {
    grid-template-columns: 1fr;
  }

  .oa-lite-workbench-sidebar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px;
    padding: 0;
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

  .oa-lite-workbench-sidebar {
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
