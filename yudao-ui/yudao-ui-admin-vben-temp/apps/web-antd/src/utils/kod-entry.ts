import type { LocationQuery, LocationQueryRaw } from 'vue-router';

import type { MenuRecordRaw } from '@vben/types';

import { isAdminUser, resolveAdminHomePath, resolveUserHomePath } from '#/utils/oa-user';

const KOD_ENTRY_APPROVAL = 'approval';
const KOD_ENTRY_PARTY_FILE = 'party-file';
const KOD_ENTRY_MEETING_ROOM = 'meeting-room';
const KOD_ENTRY_SCHEDULE = 'schedule';
const OA_LITE_FORCE_CREATE_QUERY_KEY = 'forceCreate';

type KodEntry =
  | typeof KOD_ENTRY_APPROVAL
  | typeof KOD_ENTRY_PARTY_FILE
  | typeof KOD_ENTRY_MEETING_ROOM
  | typeof KOD_ENTRY_SCHEDULE;

type StandaloneRootMenuPath =
  | '/meeting-room'
  | '/party-file'
  | '/schedule';

const MEETING_CENTER_MENU_PATHS = new Set([
  '/meeting-room/manage',
  '/meeting-room/booking',
  '/meeting-room/schedule',
]);

const MEETING_CENTER_MENU_ITEMS: MenuRecordRaw[] = [
  {
    name: '会议室管理',
    path: '/meeting-room/manage',
  },
  {
    name: '会议室预定',
    path: '/meeting-room/booking',
  },
  {
    name: '会议室排期',
    path: '/meeting-room/schedule',
  },
];

const SCHEDULE_CENTER_MENU_PATHS = new Set([
  '/schedule/calendar',
]);

const SCHEDULE_CENTER_MENU_ITEMS: MenuRecordRaw[] = [
  {
    name: '个人日程',
    path: '/schedule/calendar',
  },
];

const PARTY_FILE_CENTER_MENU_PATHS = new Set([
  '/party-file/manage',
  '/party-file/my',
]);

const PARTY_FILE_CENTER_MENU_ITEMS: MenuRecordRaw[] = [
  {
    name: '党务文件管理',
    path: '/party-file/manage',
  },
  {
    name: '我的党务文件',
    path: '/party-file/my',
  },
];

const STANDALONE_FULLSCREEN_PATH_PREFIXES = [
  '/meeting-room',
  '/schedule',
  '/party-file',
];

function readQueryString(query: LocationQuery | LocationQueryRaw, name: string) {
  const value = query[name];
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return typeof normalizedValue === 'string' ? normalizedValue : null;
}

function resolveKodEntryFromQuery(query: LocationQuery | LocationQueryRaw): KodEntry | null {
  const entry = readQueryString(query, 'entry');
  if (
    entry === KOD_ENTRY_APPROVAL ||
    entry === KOD_ENTRY_PARTY_FILE ||
    entry === KOD_ENTRY_MEETING_ROOM ||
    entry === KOD_ENTRY_SCHEDULE
  ) {
    return entry;
  }
  return null;
}

function isForceCreateEntry(query: LocationQuery | LocationQueryRaw) {
  return readQueryString(query, OA_LITE_FORCE_CREATE_QUERY_KEY) === '1';
}

function isApprovalEntryQuery(query: LocationQuery | LocationQueryRaw) {
  return resolveKodEntryFromQuery(query) === KOD_ENTRY_APPROVAL;
}

function buildApprovalEntryPath(
  normalizedRedirect: null | string,
  query: LocationQuery | LocationQueryRaw,
  userHomePath: string | undefined,
  userRoles: string[] = [],
) {
  const forceCreateQuery = isForceCreateEntry(query)
    ? `${OA_LITE_FORCE_CREATE_QUERY_KEY}=1`
    : '';
  if (normalizedRedirect) {
    return normalizedRedirect.startsWith('/oa-lite')
      ? `${normalizedRedirect}${normalizedRedirect.includes('?') ? '&' : '?'}entry=${KOD_ENTRY_APPROVAL}${forceCreateQuery ? `&${forceCreateQuery}` : ''}`
      : normalizedRedirect;
  }
  if (forceCreateQuery) {
    return `/oa-lite?entry=${KOD_ENTRY_APPROVAL}&${forceCreateQuery}`;
  }
  if (isAdminUser(userRoles)) {
    return resolveAdminHomePath(userHomePath);
  }
  const approvalPath = resolveUserHomePath(userHomePath, userRoles);
  return approvalPath.startsWith('/oa-lite')
    ? `${approvalPath}${approvalPath.includes('?') ? '&' : '?'}entry=${KOD_ENTRY_APPROVAL}`
    : `${approvalPath}?entry=${KOD_ENTRY_APPROVAL}`;
}

function resolveKodEntryTarget(
  query: LocationQuery | LocationQueryRaw,
  userHomePath: string | undefined,
  userRoles: string[] = [],
) {
  const entry = resolveKodEntryFromQuery(query);
  const redirect = readQueryString(query, 'redirect');
  const normalizedRedirect = redirect && redirect.startsWith('/') ? redirect : null;
  switch (entry) {
    case KOD_ENTRY_APPROVAL:
      return buildApprovalEntryPath(normalizedRedirect, query, userHomePath, userRoles);
    case KOD_ENTRY_PARTY_FILE:
      return normalizedRedirect || '/party-file/my';
    case KOD_ENTRY_MEETING_ROOM:
      return normalizedRedirect || '/meeting-room/booking';
    case KOD_ENTRY_SCHEDULE:
      return normalizedRedirect || '/schedule/calendar';
    default:
      return normalizedRedirect || resolveUserHomePath(userHomePath, userRoles);
  }
}

function buildKodEntryQuery(
  entry: KodEntry,
  extraQuery: LocationQuery | LocationQueryRaw = {},
): LocationQueryRaw {
  return {
    ...extraQuery,
    entry,
  };
}

function buildApprovalEntryBackRoute(
  query: LocationQuery | LocationQueryRaw,
  routeName = 'OALite',
) {
  return isApprovalEntryQuery(query)
    ? { name: routeName, query: buildKodEntryQuery(KOD_ENTRY_APPROVAL, query) }
    : { name: routeName };
}

function resolveStandaloneRootMenuPath(path: string): StandaloneRootMenuPath | '' {
  if (path === '/meeting-room' || path.startsWith('/meeting-room/')) {
    return '/meeting-room';
  }
  if (path === '/schedule' || path.startsWith('/schedule/')) {
    return '/schedule';
  }
  if (path === '/party-file' || path.startsWith('/party-file/')) {
    return '/party-file';
  }
  return '';
}

function isStandaloneWorkspacePath(path: string) {
  return STANDALONE_FULLSCREEN_PATH_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

function getStandaloneCenterRootMenu(
  rootMenuPath: StandaloneRootMenuPath,
): MenuRecordRaw | null {
  switch (rootMenuPath) {
    case '/meeting-room':
      return {
        name: '会议室',
        path: '/meeting-room',
        children: MEETING_CENTER_MENU_ITEMS,
      };
    case '/schedule':
      return {
        name: '日程',
        path: '/schedule',
        children: SCHEDULE_CENTER_MENU_ITEMS,
      };
    case '/party-file':
      return {
        name: '党务管理',
        path: '/party-file',
        children: PARTY_FILE_CENTER_MENU_ITEMS,
      };
    default:
      return null;
  }
}

function getStandaloneCenterMenuItems(rootMenuPath: StandaloneRootMenuPath) {
  switch (rootMenuPath) {
    case '/meeting-room':
      return MEETING_CENTER_MENU_ITEMS;
    case '/schedule':
      return SCHEDULE_CENTER_MENU_ITEMS;
    case '/party-file':
      return PARTY_FILE_CENTER_MENU_ITEMS;
    default:
      return [];
  }
}

function getStandaloneCenterMenuPathSet(rootMenuPath: StandaloneRootMenuPath) {
  switch (rootMenuPath) {
    case '/meeting-room':
      return MEETING_CENTER_MENU_PATHS;
    case '/schedule':
      return SCHEDULE_CENTER_MENU_PATHS;
    case '/party-file':
      return PARTY_FILE_CENTER_MENU_PATHS;
    default:
      return new Set<string>();
  }
}

export {
  KOD_ENTRY_APPROVAL,
  KOD_ENTRY_MEETING_ROOM,
  KOD_ENTRY_PARTY_FILE,
  KOD_ENTRY_SCHEDULE,
  PARTY_FILE_CENTER_MENU_ITEMS,
  OA_LITE_FORCE_CREATE_QUERY_KEY,
  SCHEDULE_CENTER_MENU_ITEMS,
  MEETING_CENTER_MENU_ITEMS,
  buildKodEntryQuery,
  buildApprovalEntryBackRoute,
  getStandaloneCenterMenuItems,
  getStandaloneCenterMenuPathSet,
  getStandaloneCenterRootMenu,
  isApprovalEntryQuery,
  isForceCreateEntry,
  isStandaloneWorkspacePath,
  resolveKodEntryFromQuery,
  resolveKodEntryTarget,
  resolveStandaloneRootMenuPath,
};
