<script lang="ts" setup>
import type { SystemPartyFileApi } from '#/api/system/party-file';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { downloadFileFromBlobPart, formatDateTime } from '@vben/utils';
import { Button, Empty, Modal as AntModal, Tag } from 'ant-design-vue';

import {
  downloadMyPartyFileAttachment,
  downloadPartyFileAttachment,
  getMyPartyFileAttachmentPreviewUrl,
  getMyPartyFile,
  getPartyFileAttachmentPreviewUrl,
  getPartyFile,
} from '#/api/system/party-file';
import { getOaFilePreviewUrl, normalizeOaAssetUrl } from '#/utils';

const detail = ref<SystemPartyFileApi.PartyFile>();
const isMine = ref(false);
const previewOpen = ref(false);
const previewLoading = ref(false);
const previewUrl = ref('');
const previewTitle = ref('附件预览');

const [Modal, modalApi] = useVbenModal({
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      detail.value = undefined;
      isMine.value = false;
      return;
    }
    const data = modalApi.getData<{ id: number; mine?: boolean }>();
    if (!data?.id) {
      return;
    }
    isMine.value = Boolean(data.mine);
    modalApi.lock();
    try {
      detail.value = isMine.value
        ? await getMyPartyFile(data.id)
        : await getPartyFile(data.id);
    } finally {
      modalApi.unlock();
    }
  },
});

const attachmentCount = computed(() => detail.value?.attachments?.length || 0);
const targetSummary = computed(() => {
  const targets = detail.value?.targets || [];
  if (!targets.length) {
    return '-';
  }
  return targets.map((item) => item.targetName || '未命名对象').join('、');
});
const formattedPublishTime = computed(() =>
  detail.value?.publishTime ? formatDateTime(detail.value.publishTime) : '-',
);
const formattedCreateTime = computed(() =>
  detail.value?.createTime ? formatDateTime(detail.value.createTime) : '-',
);
const readSummaryText = computed(() =>
  `已有 ${detail.value?.readCount || 0} 人阅读了该通知，${detail.value?.unreadCount || 0} 人未读`,
);

function formatReadTime(value?: Date | string) {
  return value ? formatDateTime(value) : '-';
}

function formatReadSource(source?: number) {
  switch (source) {
    case 2: {
      return '下载附件';
    }
    case 3: {
      return '预览附件';
    }
    default: {
      return '查看详情';
    }
  }
}

function getReadSourceTagColor(source?: number) {
  switch (source) {
    case 2: {
      return 'blue';
    }
    case 3: {
      return 'purple';
    }
    default: {
      return 'green';
    }
  }
}

function formatFileSize(size?: number) {
  if (!size || size <= 0) {
    return '';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  let current = size;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  return `${current >= 100 ? current.toFixed(0) : current.toFixed(2).replace(/\.?0+$/, '')} ${units[unitIndex]}`;
}

function getFileExtension(name: string) {
  return name.includes('.')
    ? name.split('.').pop()?.toUpperCase() || 'FILE'
    : 'FILE';
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
  if (['PNG', 'JPG', 'JPEG', 'GIF', 'WEBP', 'SVG'].includes(extension)) {
    return 'lucide:image';
  }
  return 'lucide:file';
}

async function handleDownload(fileId: number) {
  if (!detail.value?.id) {
    return;
  }
  const attachment = detail.value.attachments?.find((item) => item.id === fileId);
  const fileName = attachment?.name || '附件';
  const data = isMine.value
    ? await downloadMyPartyFileAttachment(detail.value.id, fileId)
    : await downloadPartyFileAttachment(detail.value.id, fileId);
  downloadFileFromBlobPart({ fileName, source: data });
}

async function handlePreview(fileId: number) {
  if (!detail.value?.id) {
    return;
  }
  const attachment = detail.value.attachments?.find((item) => item.id === fileId);
  previewTitle.value = attachment?.name || '附件预览';
  previewOpen.value = true;
  previewLoading.value = true;
  previewUrl.value = '';
  try {
    const sourceUrl = isMine.value
      ? await getMyPartyFileAttachmentPreviewUrl(detail.value.id, fileId)
      : await getPartyFileAttachmentPreviewUrl(detail.value.id, fileId);
    previewUrl.value = getOaFilePreviewUrl(normalizeOaAssetUrl(sourceUrl));
  } finally {
    previewLoading.value = false;
  }
}
</script>

<template>
  <Modal title="党务文件详情" class="w-[1180px]">
    <div v-if="detail" class="party-file-detail">
      <section class="party-file-detail__main">
        <header class="party-file-detail__title-bar">
          <h2>{{ detail.title }}</h2>
        </header>

        <div class="party-file-detail__meta-line">
          <div class="party-file-detail__meta-item">
            <span class="party-file-detail__meta-label">发布人：</span>
            <span class="party-file-detail__meta-value">{{ detail.creator || '-' }}</span>
          </div>
          <div class="party-file-detail__meta-item party-file-detail__meta-item--right">
            <span class="party-file-detail__meta-label">发布日期：</span>
            <span class="party-file-detail__meta-value">{{ formattedPublishTime }}</span>
          </div>
        </div>

        <section v-if="detail.summary" class="party-file-detail__summary">
          <span class="party-file-detail__summary-label">内容摘要：</span>
          <span class="party-file-detail__summary-text">{{ detail.summary }}</span>
        </section>

        <section class="party-file-detail__content">
          <div v-html="detail.content || '<p>暂无正文</p>'"></div>
        </section>
      </section>

      <aside class="party-file-detail__sidebar">
        <section class="party-file-detail__panel">
          <div class="party-file-detail__panel-title">其他信息</div>
          <dl class="party-file-detail__info-list">
            <div>
              <dt>通知分类：</dt>
              <dd>{{ detail.categoryName || '-' }}</dd>
            </div>
            <div>
              <dt>分发对象：</dt>
              <dd>{{ targetSummary }}</dd>
            </div>
            <div v-if="isMine">
              <dt>是否已读：</dt>
              <dd>
                <Tag :color="detail.readStatus ? 'success' : 'processing'">
                  {{ detail.readStatus ? '是' : '否' }}
                </Tag>
              </dd>
            </div>
            <div>
              <dt>发布人：</dt>
              <dd>{{ detail.creator || '-' }}</dd>
            </div>
            <div>
              <dt>创建时间：</dt>
              <dd>{{ formattedCreateTime }}</dd>
            </div>
          </dl>
        </section>

        <section class="party-file-detail__panel">
          <div class="party-file-detail__panel-head">
            <div class="party-file-detail__panel-title">附件信息</div>
            <span v-if="attachmentCount" class="party-file-detail__panel-extra">
              共 {{ attachmentCount }} 个
            </span>
          </div>
          <div v-if="attachmentCount" class="party-file-detail__attachments">
            <div
              v-for="item in detail.attachments"
              :key="item.id"
              class="party-file-detail__attachment"
            >
              <span class="party-file-detail__attachment-icon">
                <IconifyIcon :icon="getFileIcon(item.name)" />
              </span>
              <div class="party-file-detail__attachment-body">
                <div class="party-file-detail__attachment-name">{{ item.name }}</div>
                <div class="party-file-detail__attachment-meta">
                  {{ formatFileSize(item.size) || '未知大小' }}
                </div>
              </div>
              <div class="party-file-detail__attachment-actions">
                <Button type="link" size="small" @click="handlePreview(item.id)">
                  预览
                </Button>
                <Button type="link" size="small" @click="handleDownload(item.id)">
                  下载
                </Button>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="暂无附件" />
        </section>

        <section v-if="!isMine" class="party-file-detail__panel">
          <div class="party-file-detail__panel-head">
            <div class="party-file-detail__panel-title">阅读列表</div>
            <span class="party-file-detail__panel-extra">
              {{ readSummaryText }}
            </span>
          </div>
          <div v-if="detail.readList?.length" class="party-file-detail__read-list">
            <div
              v-for="item in detail.readList"
              :key="`${item.userId}-${item.readTime}`"
              class="party-file-detail__read-item"
            >
              <div class="party-file-detail__avatar">
                {{ item.userNickname?.slice(0, 1) || '?' }}
              </div>
              <div class="party-file-detail__read-content">
                <div class="party-file-detail__read-name">
                  {{ item.userNickname }}
                  <span v-if="item.deptName">（{{ item.deptName }}）</span>
                </div>
                <div class="party-file-detail__read-time">
                  <span>{{ formatReadTime(item.readTime) }}</span>
                  <Tag
                    :color="getReadSourceTagColor(item.readSource)"
                    class="party-file-detail__read-tag"
                  >
                    {{ formatReadSource(item.readSource) }}
                  </Tag>
                </div>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="暂无阅读记录" />
        </section>

        <section v-if="!isMine" class="party-file-detail__panel">
          <div class="party-file-detail__panel-head">
            <div class="party-file-detail__panel-title">未读列表</div>
            <span class="party-file-detail__panel-extra">
              {{ detail.unreadCount || 0 }} 人未读
            </span>
          </div>
          <div v-if="detail.unreadList?.length" class="party-file-detail__unread-list">
            <div
              v-for="item in detail.unreadList"
              :key="item.userId"
              class="party-file-detail__unread-item"
            >
              <div class="party-file-detail__avatar party-file-detail__avatar--muted">
                {{ item.userNickname?.slice(0, 1) || '?' }}
              </div>
              <div class="party-file-detail__read-content">
                <div class="party-file-detail__read-name">
                  {{ item.userNickname }}
                </div>
                <div class="party-file-detail__read-time">
                  <span v-if="item.deptName">{{ item.deptName }}</span>
                  <span v-else>暂无部门信息</span>
                </div>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="全部已读" />
        </section>
      </aside>
    </div>
  </Modal>

  <AntModal
    v-model:open="previewOpen"
    :footer="null"
    :title="previewTitle"
    width="900px"
    destroy-on-close
  >
    <div v-if="previewLoading" class="party-file-preview-loading">正在加载预览...</div>
    <iframe
      v-else-if="previewUrl"
      :src="previewUrl"
      :title="`预览 ${previewTitle}`"
      class="party-file-preview-frame"
    />
  </AntModal>
</template>

<style scoped>
.party-file-detail {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  min-height: 640px;
}

.party-file-detail__main,
.party-file-detail__panel {
  border: 1px solid rgb(15 23 42 / 8%);
  background: #fff;
}

.party-file-detail__main {
  min-width: 0;
}

.party-file-detail__title-bar {
  padding: 10px 16px;
  border-bottom: 1px solid rgb(15 23 42 / 10%);
  background: linear-gradient(180deg, #f0f0f0 0%, #d9d9d9 100%);
}

.party-file-detail__title-bar h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: rgb(15 23 42);
}

.party-file-detail__meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 8px;
  color: rgb(71 85 105);
  font-size: 13px;
}

.party-file-detail__meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.party-file-detail__meta-item--right {
  margin-left: auto;
}

.party-file-detail__meta-label {
  color: rgb(100 116 139);
}

.party-file-detail__meta-value {
  color: rgb(14 116 144);
}

.party-file-detail__summary {
  padding: 0 16px 12px;
  color: rgb(51 65 85);
  font-size: 13px;
  border-bottom: 1px solid rgb(15 23 42 / 6%);
}

.party-file-detail__summary-label {
  color: rgb(100 116 139);
}

.party-file-detail__content {
  padding: 16px;
  color: rgb(30 41 59);
  line-height: 1.9;
  font-size: 15px;
}

.party-file-detail__content :deep(p) {
  margin: 0 0 14px;
}

.party-file-detail__sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.party-file-detail__panel {
  padding: 12px;
}

.party-file-detail__panel-title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(71 85 105);
}

.party-file-detail__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgb(15 23 42 / 8%);
}

.party-file-detail__panel-extra {
  color: rgb(100 116 139);
  font-size: 12px;
}

.party-file-detail__info-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0 0;
}

.party-file-detail__info-list div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
}

.party-file-detail__info-list dt {
  color: rgb(100 116 139);
}

.party-file-detail__info-list dd {
  margin: 0;
  color: rgb(30 41 59);
  word-break: break-word;
}

.party-file-detail__attachments,
.party-file-detail__read-list,
.party-file-detail__unread-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 260px;
  overflow: auto;
  padding-right: 4px;
}

.party-file-detail__attachment,
.party-file-detail__read-item,
.party-file-detail__unread-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(15 23 42 / 6%);
}

.party-file-detail__attachment {
  padding: 10px 12px;
  border: 1px solid rgb(15 23 42 / 8%);
  border-radius: 8px;
  background: rgb(248 250 252);
}

.party-file-detail__attachment:last-child,
.party-file-detail__read-item:last-child,
.party-file-detail__unread-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.party-file-detail__attachment:first-child,
.party-file-detail__read-item:first-child,
.party-file-detail__unread-item:first-child {
  padding-top: 0;
}

.party-file-detail__attachment:first-child {
  padding-top: 10px;
}

.party-file-detail__attachment:last-child {
  padding-bottom: 10px;
}

.party-file-detail__attachment-icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgb(219 234 254);
  color: rgb(37 99 235);
  font-size: 20px;
}

.party-file-detail__attachment-body,
.party-file-detail__read-content {
  min-width: 0;
  flex: 1;
}

.party-file-detail__attachment-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.party-file-detail__attachment-name,
.party-file-detail__read-name {
  color: rgb(30 41 59);
  font-size: 14px;
  word-break: break-word;
}

.party-file-detail__attachment-meta,
.party-file-detail__read-time {
  margin-top: 4px;
  color: rgb(100 116 139);
  font-size: 12px;
}

.party-file-detail__read-time {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.party-file-detail__read-tag {
  margin-inline-end: 0;
}

.party-file-detail__avatar {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #16a34a;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.party-file-detail__avatar--muted {
  background: #64748b;
}

.party-file-detail__unread-item {
  align-items: center;
}

.party-file-preview-loading {
  display: grid;
  min-height: 420px;
  place-items: center;
  color: #64748b;
}

.party-file-preview-frame {
  display: block;
  width: 100%;
  height: 70vh;
  border: 0;
}

@media (max-width: 960px) {
  .party-file-detail {
    grid-template-columns: minmax(0, 1fr);
  }

  .party-file-detail__meta-item--right {
    margin-left: 0;
  }
}
</style>
