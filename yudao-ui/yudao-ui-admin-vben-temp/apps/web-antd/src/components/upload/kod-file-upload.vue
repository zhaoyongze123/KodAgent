<script lang="ts" setup>
import type { FileUploadProps } from './typing';

import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccessStore } from '@vben/stores';
import { Button, Modal, Table, TreeSelect, message } from 'ant-design-vue';

import type { SystemPartyFileApi } from '#/api/system/party-file';

import {
  getCurrentUserPartyFileKodFiles,
  getCurrentUserPartyFileKodFolderChildren,
  getPartyFileAttachmentAccessUrl,
  selectCurrentUserPartyFileKodFiles,
} from '#/api/system/party-file';

import FileUpload from './file-upload.vue';

type FileUploadValue = FileUploadProps['modelValue'];

const props = withDefaults(
  defineProps<{
    accept?: string[];
    disabled?: boolean | (() => boolean);
    maxNumber?: number;
    maxSize?: number;
    modelValue?: FileUploadValue;
    multiple?: boolean;
  }>(),
  {
    accept: () => [],
    disabled: false,
    maxNumber: 10,
    maxSize: 2,
    modelValue: undefined,
    multiple: true,
  },
);

const emit = defineEmits<{
  change: [value: FileUploadValue];
  'update:modelValue': [value: FileUploadValue];
}>();

const AUTH_KOD_SSO_TOKEN_INVALID_CODE = 1_002_000_011;
const PARTY_FILE_KOD_REQUEST_FAILED_CODE = 1_002_009_017;
let kodSsoRefreshInFlight = false;

const route = useRoute();
const router = useRouter();
const accessStore = useAccessStore();

const fileValue = ref<Array<Record<string, any> | string>>([]);
const kodFolderPath = ref('/');
const kodFolderTree = ref<SystemPartyFileApi.PartyFileKodFolder[]>([]);
const kodFileList = ref<SystemPartyFileApi.PartyFileKodFile[]>([]);
const selectedKodFilePaths = ref<string[]>([]);
const selectedKodFiles = ref<SystemPartyFileApi.PartyFileKodFile[]>([]);
const kodFileModalOpen = ref(false);
const kodFileLoading = ref(false);

const kodFileColumns = [
  { title: '文件名', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '大小', dataIndex: 'size', key: 'size', width: 120 },
  { title: '路径', dataIndex: 'pathDisplay', key: 'pathDisplay', ellipsis: true },
];

function normalizeValue(value: FileUploadValue) {
  if (value === undefined || value === null || value === '') {
    return [];
  }
  if (Array.isArray(value)) {
    return value as Array<Record<string, any> | string>;
  }
  if (typeof value === 'string' && value.includes(',')) {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [value as Record<string, any> | string];
}

function emitValue(value: Array<Record<string, any> | string>) {
  fileValue.value = value;
  emit('update:modelValue', value);
  emit('change', value);
}

function isSameFile(left: Record<string, any> | string, right: Record<string, any>) {
  if (typeof left === 'string') {
    return left === right.url;
  }
  return Number(left.id) > 0 && Number(left.id) === Number(right.id);
}

function getKodErrorCode(error: any) {
  return Number(error?.code ?? error?.data?.code ?? error?.response?.data?.code);
}

function getKodErrorMessage(error: any) {
  return String(
    error?.msg ??
      error?.message ??
      error?.data?.msg ??
      error?.response?.data?.msg ??
      '',
  );
}

function isKodTokenInvalidError(error: any) {
  const code = getKodErrorCode(error);
  if (code === AUTH_KOD_SSO_TOKEN_INVALID_CODE) {
    return true;
  }
  if (code !== PARTY_FILE_KOD_REQUEST_FAILED_CODE) {
    return false;
  }
  return /令牌已失效|令牌无效|重新登录可道云|可道云登录失败/i.test(
    getKodErrorMessage(error),
  );
}

function buildKodSsoCallbackUrl() {
  const callbackRoute = router.resolve({
    path: '/auth/kod-sso-login',
    query: {
      tenantId: String(accessStore.tenantId || 1),
      redirect: route.fullPath,
    },
  });
  return new URL(callbackRoute.href, window.location.origin).toString();
}

function redirectToKodSsoOnTokenInvalid(error: any) {
  if (!isKodTokenInvalidError(error) || kodSsoRefreshInFlight) {
    return false;
  }
  kodSsoRefreshInFlight = true;
  message.info('可道云登录已失效，正在重新登录，请稍候…');
  const startUrl = `/admin-api/system/auth/kod-sso/start?redirectUri=${encodeURIComponent(
    buildKodSsoCallbackUrl(),
  )}`;
  window.location.replace(startUrl);
  return true;
}

function findKodFolderNode(
  nodes: SystemPartyFileApi.PartyFileKodFolder[],
  key: string,
): SystemPartyFileApi.PartyFileKodFolder | undefined {
  for (const node of nodes) {
    if (node.key === key) {
      return node;
    }
    const found = node.children && findKodFolderNode(node.children, key);
    if (found) {
      return found;
    }
  }
  return undefined;
}

async function loadKodFolderChildren(node: any) {
  const folder = (node?.dataRef ?? node) as SystemPartyFileApi.PartyFileKodFolder;
  const path = folder.path || folder.value || folder.key;
  if (!path) {
    return;
  }
  try {
    const children = await getCurrentUserPartyFileKodFolderChildren({
      kodFolderPath: path,
    });
    const target = findKodFolderNode(kodFolderTree.value, folder.key || path);
    if (target) {
      target.children = children;
      target.isLeaf = children.length === 0;
    }
  } catch (error) {
    if (redirectToKodSsoOnTokenInvalid(error)) {
      return;
    }
    message.error('可道云子目录加载失败，请稍后重试');
    throw error;
  }
}

async function loadKodFiles() {
  if (!kodFolderPath.value) {
    message.warning('请选择可道云目录');
    return;
  }
  kodFileLoading.value = true;
  try {
    kodFileList.value = await getCurrentUserPartyFileKodFiles({
      kodFolderPath: kodFolderPath.value,
    });
    selectedKodFilePaths.value = [];
    selectedKodFiles.value = [];
  } finally {
    kodFileLoading.value = false;
  }
}

function handleKodFileSelectionChange(
  keys: Array<number | string>,
  rows: SystemPartyFileApi.PartyFileKodFile[],
) {
  selectedKodFilePaths.value = keys.map(String);
  selectedKodFiles.value = rows;
}

async function confirmKodFileSelection() {
  if (!kodFolderPath.value) {
    message.warning('请选择可道云目录');
    return;
  }
  if (!selectedKodFiles.value.length) {
    message.warning('请至少选择一个可道云文件');
    return;
  }
  const existingCount = fileValue.value.length;
  if (existingCount + selectedKodFiles.value.length > props.maxNumber) {
    message.error(`最多只能选择 ${props.maxNumber} 个文件`);
    return;
  }
  kodFileLoading.value = true;
  try {
    const attachments = await selectCurrentUserPartyFileKodFiles({
      files: selectedKodFiles.value,
      kodFolderPath: kodFolderPath.value,
    });
    const incoming = attachments.map((item) => ({
      ...item,
      status: 'done',
      uid: `kod-${item.id}`,
      url: item.id ? getPartyFileAttachmentAccessUrl(item.id) : item.url,
    }));
    const merged = [...fileValue.value];
    incoming.forEach((item) => {
      if (!merged.some((current) => isSameFile(current, item))) {
        merged.push(item);
      }
    });
    emitValue(merged);
    kodFileModalOpen.value = false;
    message.success('已添加可道云文件');
  } catch (error) {
    if (redirectToKodSsoOnTokenInvalid(error)) {
      return;
    }
    throw error;
  } finally {
    kodFileLoading.value = false;
  }
}

function handleFileValueChange(value: FileUploadValue) {
  emitValue(normalizeValue(value));
}

watch(
  () => props.modelValue,
  (value) => {
    fileValue.value = normalizeValue(value);
  },
  { deep: true, immediate: true },
);
</script>

<template>
  <div class="kod-file-upload">
    <FileUpload
      :accept="accept"
      :disabled="disabled"
      :max-number="maxNumber"
      :max-size="maxSize"
      :model-value="fileValue"
      :multiple="multiple"
      @update:model-value="handleFileValueChange"
    />

    <Modal
      v-model:open="kodFileModalOpen"
      title="从可道云选择文件"
      width="920px"
      :confirm-loading="kodFileLoading"
      @ok="confirmKodFileSelection"
    >
      <div class="kod-file-picker-toolbar">
        <TreeSelect
          v-model:value="kodFolderPath"
          class="kod-file-picker-folder"
          placeholder="选择目录"
          :tree-data="kodFolderTree"
          :field-names="{ children: 'children', label: 'title', value: 'value' }"
          :load-data="loadKodFolderChildren"
          show-search
          @change="loadKodFiles"
        />
        <Button :loading="kodFileLoading" @click="loadKodFiles">刷新</Button>
      </div>
      <Table
        :columns="kodFileColumns"
        :data-source="kodFileList"
        :loading="kodFileLoading"
        :pagination="false"
        row-key="path"
        :row-selection="{
          selectedRowKeys: selectedKodFilePaths,
          onChange: handleKodFileSelectionChange,
        }"
        size="small"
      />
    </Modal>
  </div>
</template>

<style scoped>
.kod-file-picker-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
}

.kod-file-picker-folder {
  min-width: 0;
  flex: 1;
}
</style>
