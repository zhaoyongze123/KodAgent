<script lang="ts" setup>
import type { ComplexFieldConfig, ComplexOAModuleKey } from './config';

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { ContentWrap } from '@vben/common-ui';

import { Button, Modal, Spin, Tag } from 'ant-design-vue';

import { IconifyIcon } from '@vben/icons';

import { getDictOptions } from '@vben/hooks';
import { DICT_TYPE } from '@vben/constants';

import { getPartyFileAttachmentPreviewUrlByFileId } from '#/api/system/party-file';
import { formatFlowFormDateTime } from '#/components/form-create';
import { getOaFilePreviewUrl, normalizeOaAssetUrl } from '#/utils';
import { getComplexModuleViewConfig, parseJsonArray } from './config';

defineOptions({ name: 'OAComplexDetailPage' });

const props = defineProps<{
  id?: string;
  moduleKey: ComplexOAModuleKey;
}>();

const route = useRoute();
const config = getComplexModuleViewConfig(props.moduleKey);
const loading = ref(false);
const detailData = ref<Record<string, any>>({});
type DetailFile = { id?: number; name: string; size: number; url: string };
const previewFile = ref<null | (DetailFile & { previewUrl: string })>(null);

const queryId = computed(() => Number(props.id || route.query.id));

const statusDict = computed(() => getDictOptions(DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS, 'number'));

function getStatusText(status?: number) {
  const matched = statusDict.value.find((item) => item.value === status);
  return matched?.label || '-';
}

function getStatusColor(status?: number) {
  switch (status) {
    case 1:
      return 'processing';
    case 2:
      return 'success';
    case 3:
      return 'error';
    case 4:
      return 'default';
    default:
      return 'default';
  }
}

function getSelectLabel(field: ComplexFieldConfig, value: unknown) {
  const matched = field.options?.find((item) => String(item.value) === String(value));
  return matched?.label || value || '-';
}

function renderValue(field: ComplexFieldConfig) {
  const value = detailData.value[field.field];
  if (field.type === 'datetime') {
    return formatFlowFormDateTime(value) || '-';
  }
  if (field.type === 'select') {
    return getSelectLabel(field, value);
  }
  if (field.type === 'switch') {
    return value ? '是' : '否';
  }
  if (field.type === 'files') {
    const files = parseJsonArray(value);
    return files.length > 0 ? files : [];
  }
  return value || '-';
}

function getFileName(rawValue: unknown) {
  const raw =
    rawValue && typeof rawValue === 'object'
      ? String(
          (rawValue as Record<string, unknown>).name ||
            (rawValue as Record<string, unknown>).url ||
            (rawValue as Record<string, unknown>).fileUrl ||
            '',
        )
      : String(rawValue || '');
  const withoutQuery = raw.split(/[?#]/, 1)[0] || raw;
  const lastPart = withoutQuery.slice(withoutQuery.lastIndexOf('/') + 1);
  try {
    return decodeURIComponent(lastPart) || '未命名文件';
  } catch {
    return lastPart || '未命名文件';
  }
}

function getDetailFiles(field: ComplexFieldConfig) {
  return parseJsonArray(detailData.value[field.field])
    .map((rawValue) => {
      const record = rawValue && typeof rawValue === 'object'
        ? (rawValue as Record<string, unknown>)
        : undefined;
      const id = Number(record?.id || record?.fileId || 0);
      return {
        id: id > 0 ? id : undefined,
        name: getFileName(rawValue),
        size: Number(record?.size || 0),
        url: normalizeOaAssetUrl(
          record
            ? String(record.url || record.fileUrl || '')
            : String(rawValue || ''),
        ),
      };
    })
    .filter((file) => file.url);
}

const visibleDetailFields = computed(() =>
  config.detailFields.filter((field) => {
    const value = detailData.value[field.field];
    if (field.type === 'files') {
      return getDetailFiles(field).length > 0;
    }
    return value !== undefined && value !== null && String(value).trim() !== '';
  }),
);

function getFileExtension(name: string) {
  return name.includes('.') ? name.split('.').pop()?.toUpperCase() || 'FILE' : 'FILE';
}

function formatFileSize(size?: number) {
  if (!size || size <= 0) {
    return '';
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function getFileIcon(name: string) {
  const extension = getFileExtension(name);
  if (extension === 'PDF') {
    return 'lucide:file-type-2';
  }
  if (['DOC', 'DOCX', 'TXT'].includes(extension)) {
    return 'lucide:file-text';
  }
  if (['XLS', 'XLSX', 'CSV'].includes(extension)) {
    return 'lucide:file-spreadsheet';
  }
  if (['PNG', 'JPG', 'JPEG', 'GIF', 'WEBP'].includes(extension)) {
    return 'lucide:image';
  }
  return 'lucide:file';
}

async function getPreviewUrl(file: DetailFile) {
  const sourceUrl = file.id && file.url.includes('/system/party-file/attachment/access')
    ? await getPartyFileAttachmentPreviewUrlByFileId(file.id)
    : file.url;
  return getOaFilePreviewUrl(sourceUrl);
}

async function openFilePreview(file: DetailFile) {
  try {
    previewFile.value = { ...file, previewUrl: await getPreviewUrl(file) };
  } catch {
    previewFile.value = null;
  }
}

function openFileInNewWindow() {
  if (previewFile.value && typeof window !== 'undefined') {
    window.open(previewFile.value.previewUrl, '_blank', 'noopener,noreferrer');
  }
}

function downloadFile(file: { name: string; url: string }) {
  if (typeof document === 'undefined') {
    return;
  }
  const link = document.createElement('a');
  link.href = file.url;
  link.download = file.name;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function handleAttachmentKeydown(event: KeyboardEvent, file: DetailFile) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    openFilePreview(file);
  }
}

async function loadDetail() {
  loading.value = true;
  try {
    if (!Number.isSafeInteger(queryId.value) || queryId.value <= 0) {
      return;
    }
    detailData.value = await config.getDetailRequest(queryId.value);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadDetail();
});
</script>

<template>
  <ContentWrap class="m-2">
    <Spin :spinning="loading" tip="加载中...">
      <div class="oa-detail-fields">
        <div class="oa-detail-field oa-detail-status-field">
          <span class="oa-detail-field-label">审批状态</span>
          <div class="oa-detail-field-value">
          <Tag :color="getStatusColor(detailData.status)">
            {{ getStatusText(detailData.status) }}
          </Tag>
          </div>
        </div>
        <div
          v-for="field in visibleDetailFields"
          :key="field.field"
          class="oa-detail-field"
        >
          <span class="oa-detail-field-label">{{ field.label }}</span>
          <div class="oa-detail-field-value">
            <template v-if="field.type === 'files'">
            <div class="oa-detail-attachment-list">
              <div
                v-for="file in getDetailFiles(field)"
                :key="file.url"
                class="oa-detail-attachment-item"
                :title="`在线预览：${file.name}`"
                role="button"
                tabindex="0"
                @click="openFilePreview(file)"
                @keydown="handleAttachmentKeydown($event, file)"
              >
                <span class="oa-detail-attachment-icon">
                  <IconifyIcon :icon="getFileIcon(file.name)" />
                </span>
                <span class="oa-detail-attachment-main">
                  <strong>{{ file.name }}</strong>
                  <span>
                    {{ getFileExtension(file.name) }}
                    <template v-if="formatFileSize(file.size)">
                      · {{ formatFileSize(file.size) }}
                    </template>
                  </span>
                </span>
                <Button
                  type="link"
                  size="small"
                  class="oa-detail-attachment-preview"
                  @click.stop.prevent="openFilePreview(file)"
                >
                  预览
                </Button>
                <Button
                  type="link"
                  size="small"
                  class="oa-detail-attachment-download"
                  @click.stop.prevent="downloadFile(file)"
                >
                  下载
                </Button>
              </div>
            </div>
            </template>
            <span v-else class="oa-detail-text-value">
              {{ renderValue(field) }}
            </span>
          </div>
        </div>
      </div>
    </Spin>
  </ContentWrap>

  <Modal
    :open="previewFile !== null"
    :title="previewFile?.name || '文件预览'"
    :footer="null"
    width="960px"
    destroy-on-close
    @cancel="previewFile = null"
  >
    <div v-if="previewFile" class="oa-detail-preview-shell">
      <div class="oa-detail-preview-toolbar">
        <span class="oa-detail-preview-filename">{{ previewFile.name }}</span>
        <Button
          type="primary"
          size="small"
          @click="downloadFile(previewFile)"
        >
          下载文件
        </Button>
      </div>
      <iframe
        :src="previewFile.previewUrl"
        :title="`预览 ${previewFile.name}`"
        class="oa-detail-preview-frame"
      />
      <div class="oa-detail-preview-fallback">
        如果当前文件格式无法直接预览，
        <Button type="link" size="small" @click="openFileInNewWindow">
          在新窗口打开或下载
        </Button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.oa-detail-attachment-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
}

.oa-detail-fields {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.oa-detail-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 14px 0 16px;
  border-bottom: 1px solid var(--oa-shell-border, #e8edf3);
}

.oa-detail-field:first-child {
  padding-top: 0;
}

.oa-detail-field:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.oa-detail-field-label {
  color: var(--oa-ink-faint, #8b98a9);
  font-size: 12px;
  line-height: 1.5;
}

.oa-detail-field-value {
  min-width: 0;
  max-width: 100%;
  color: var(--oa-ink, #17202d);
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.oa-detail-text-value {
  display: block;
  white-space: pre-wrap;
}

.oa-detail-status-field {
  padding-bottom: 14px;
}

.oa-detail-attachment-item {
  display: flex;
  width: 100%;
  min-height: 64px;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--oa-shell-border, #e8edf3);
  border-radius: 8px;
  background: var(--oa-shell-surface-subtle, #f7f9fb);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.oa-detail-attachment-item:hover {
  border-color: color-mix(
    in srgb,
    var(--oa-accent, #2674d9) 42%,
    var(--oa-shell-border, #e8edf3)
  );
  background: color-mix(
    in srgb,
    var(--oa-accent-soft, #f0f6ff) 62%,
    var(--oa-shell-surface-subtle, #f7f9fb)
  );
}

.oa-detail-attachment-icon {
  display: inline-flex;
  width: 36px;
  height: 36px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--oa-accent-soft, #e7f1fb);
  color: var(--oa-accent, #2674d9);
  font-size: 21px;
}

.oa-detail-attachment-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 4px;
}

.oa-detail-attachment-main strong {
  display: block;
  overflow: hidden;
  min-width: 0;
  max-width: 100%;
  color: var(--oa-ink, #17202d);
  font-size: 14px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-detail-attachment-main span {
  overflow: hidden;
  color: var(--oa-ink-faint, #8b98a9);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-detail-attachment-preview {
  flex: none;
  color: var(--oa-accent, #2674d9);
}

.oa-detail-attachment-download {
  flex: none;
  color: var(--oa-accent, #2674d9);
}

.oa-detail-preview-shell {
  display: flex;
  min-height: 620px;
  flex-direction: column;
  gap: 8px;
}

.oa-detail-preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.oa-detail-preview-filename {
  min-width: 0;
  overflow: hidden;
  color: var(--oa-ink, #17202d);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-detail-preview-frame {
  width: 100%;
  min-height: 580px;
  flex: 1;
  border: 0;
  background: #f5f7fa;
}

.oa-detail-preview-fallback {
  color: #8b98a9;
  font-size: 12px;
  text-align: center;
}
</style>
