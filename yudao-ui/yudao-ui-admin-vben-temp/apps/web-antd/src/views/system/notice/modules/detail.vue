<script lang="ts" setup>
import type { SystemNoticeApi } from '#/api/system/notice';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { formatDateTime } from '@vben/utils';

import { Button, Empty, Tag } from 'ant-design-vue';

import { getNotice, readNotice } from '#/api/system/notice';

const notice = ref<SystemNoticeApi.Notice>();

const [Modal, modalApi] = useVbenModal({
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      notice.value = undefined;
      return;
    }
    const row = modalApi.getData<SystemNoticeApi.Notice>();
    if (!row?.id) {
      return;
    }
    modalApi.lock();
    try {
      await readNotice(row.id);
      notice.value = await getNotice(row.id);
    } finally {
      modalApi.unlock();
    }
  },
});

const attachmentCount = computed(() => notice.value?.attachments?.length || 0);
const targetSummary = computed(() => {
  const targets = notice.value?.targets || [];
  if (targets.length) {
    return targets.map((item) => item.targetName || '未命名对象').join('、');
  }
  return notice.value?.publishTarget || '全体后台用户';
});
const formattedPublishTime = computed(() =>
  notice.value?.createTime ? formatDateTime(notice.value.createTime) : '-',
);
const formattedCreateTime = computed(() =>
  notice.value?.createTime ? formatDateTime(notice.value.createTime) : '-',
);
const noticeSummary = computed(() => {
  const plainText = (notice.value?.content || '')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!plainText) {
    return '暂无内容摘要';
  }
  return plainText.length > 120 ? `${plainText.slice(0, 120)}...` : plainText;
});
const readSummaryText = computed(
  () => `已有 ${notice.value?.readCount || 0} 人阅读，${notice.value?.unreadCount || 0} 人未读`,
);

function handlePreview(url?: string) {
  if (!url) {
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

function handleDownload(url?: string) {
  if (!url) {
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

function handleBatchDownload() {
  notice.value?.attachments?.forEach((item) => handleDownload(item.url));
}

function formatReadTime(value?: Date | string) {
  return value ? formatDateTime(value) : '-';
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
</script>

<template>
  <Modal title="公告详情" class="w-[1180px]">
    <div v-if="notice" class="notice-detail">
      <section class="notice-detail__main">
        <header class="notice-detail__title-bar">
          <h2>{{ notice.title }}</h2>
        </header>

        <div class="notice-detail__meta-line">
          <div class="notice-detail__meta-item">
            <span class="notice-detail__meta-label">发布人：</span>
            <span class="notice-detail__meta-value">{{ notice.creator || '-' }}</span>
          </div>
          <div class="notice-detail__meta-item">
            <span class="notice-detail__meta-label">发布对象：</span>
            <span class="notice-detail__meta-value">{{ targetSummary }}</span>
          </div>
          <div class="notice-detail__meta-item notice-detail__meta-item--right">
            <span class="notice-detail__meta-label">发布时间：</span>
            <span class="notice-detail__meta-value">{{ formattedPublishTime }}</span>
          </div>
        </div>

        <section class="notice-detail__summary">
          <span class="notice-detail__summary-label">内容摘要：</span>
          <span class="notice-detail__summary-text">{{ noticeSummary }}</span>
        </section>

        <section class="notice-detail__content">
          <div v-html="notice.content || '<p>暂无正文</p>'"></div>
        </section>
      </section>

      <aside class="notice-detail__sidebar">
        <section class="notice-detail__panel">
          <div class="notice-detail__panel-title">其他信息</div>
          <dl class="notice-detail__info-list">
            <div>
              <dt>发布对象：</dt>
              <dd>{{ targetSummary }}</dd>
            </div>
            <div>
              <dt>发布人：</dt>
              <dd>{{ notice.creator || '-' }}</dd>
            </div>
            <div>
              <dt>创建时间：</dt>
              <dd>{{ formattedCreateTime }}</dd>
            </div>
            <div>
              <dt>置顶状态：</dt>
              <dd>
                <Tag :color="notice.pinned ? 'blue' : 'default'">
                  {{ notice.pinned ? '置顶' : '未置顶' }}
                </Tag>
              </dd>
            </div>
          </dl>
        </section>

        <section class="notice-detail__panel">
          <div class="notice-detail__panel-head">
            <div class="notice-detail__panel-title">附件信息</div>
            <span v-if="attachmentCount" class="notice-detail__panel-extra">
              共 {{ attachmentCount }} 个
            </span>
          </div>
          <div v-if="attachmentCount" class="notice-detail__attachments">
            <div
              v-for="item in notice.attachments"
              :key="item.id"
              class="notice-detail__attachment"
            >
              <div class="notice-detail__attachment-body">
                <div class="notice-detail__attachment-name">{{ item.name }}</div>
                <div class="notice-detail__attachment-meta">
                  {{ [item.type || '未知类型', formatFileSize(item.size)].filter(Boolean).join('，') }}
                </div>
              </div>
              <div class="notice-detail__attachment-actions">
                <Button size="small" type="link" @click="handlePreview(item.url)">
                  预览
                </Button>
                <Button size="small" type="link" @click="handleDownload(item.url)">
                  下载
                </Button>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="暂无附件" />
          <div v-if="attachmentCount > 1" class="notice-detail__batch-actions">
            <Button size="small" type="link" @click="handleBatchDownload">
              批量下载全部附件
            </Button>
          </div>
        </section>

        <section class="notice-detail__panel">
          <div class="notice-detail__panel-head">
            <div class="notice-detail__panel-title">阅读情况</div>
            <span class="notice-detail__panel-extra">
              {{ readSummaryText }}
            </span>
          </div>
          <div v-if="notice.readList?.length" class="notice-detail__read-list">
            <div
              v-for="item in notice.readList"
              :key="`${item.userId}-${item.readTime}`"
              class="notice-detail__read-item"
            >
              <div class="notice-detail__avatar">
                {{ item.userNickname?.slice(0, 1) || '?' }}
              </div>
              <div class="notice-detail__read-content">
                <div class="notice-detail__read-name">
                  {{ item.userNickname }}
                  <span v-if="item.deptName">（{{ item.deptName }}）</span>
                </div>
                <div class="notice-detail__read-time">{{ formatReadTime(item.readTime) }}</div>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="暂无阅读记录" />
        </section>

        <section class="notice-detail__panel">
          <div class="notice-detail__panel-head">
            <div class="notice-detail__panel-title">未读列表</div>
            <span class="notice-detail__panel-extra">
              {{ notice.unreadCount || 0 }} 人未读
            </span>
          </div>
          <div v-if="notice.unreadList?.length" class="notice-detail__read-list">
            <div
              v-for="item in notice.unreadList"
              :key="item.userId"
              class="notice-detail__read-item"
            >
              <div class="notice-detail__avatar notice-detail__avatar--muted">
                {{ item.userNickname?.slice(0, 1) || '?' }}
              </div>
              <div class="notice-detail__read-content">
                <div class="notice-detail__read-name">{{ item.userNickname }}</div>
                <div class="notice-detail__read-time">
                  {{ item.deptName || '暂无部门信息' }}
                </div>
              </div>
            </div>
          </div>
          <Empty v-else :image="Empty.PRESENTED_IMAGE_SIMPLE" description="全部已读" />
        </section>
      </aside>
    </div>
  </Modal>
</template>

<style scoped>
.notice-detail {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  min-height: 640px;
}

.notice-detail__main,
.notice-detail__panel {
  border: 1px solid rgb(15 23 42 / 8%);
  background: #fff;
}

.notice-detail__main {
  min-width: 0;
}

.notice-detail__title-bar {
  padding: 10px 16px;
  border-bottom: 1px solid rgb(15 23 42 / 10%);
  background: linear-gradient(180deg, #f7f7f7 0%, #e8edf3 100%);
}

.notice-detail__title-bar h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: rgb(15 23 42);
}

.notice-detail__meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 16px 8px;
  color: rgb(71 85 105);
  font-size: 13px;
}

.notice-detail__meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.notice-detail__meta-item--right {
  margin-left: auto;
}

.notice-detail__meta-label,
.notice-detail__summary-label {
  color: rgb(100 116 139);
}

.notice-detail__meta-value {
  color: rgb(14 116 144);
}

.notice-detail__summary {
  padding: 0 16px 12px;
  color: rgb(51 65 85);
  font-size: 13px;
  border-bottom: 1px solid rgb(15 23 42 / 6%);
}

.notice-detail__summary-text {
  color: rgb(51 65 85);
}

.notice-detail__content {
  padding: 16px;
  color: rgb(30 41 59);
  line-height: 1.9;
  font-size: 15px;
}

.notice-detail__content :deep(p) {
  margin: 0 0 14px;
}

.notice-detail__sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.notice-detail__panel {
  padding: 12px;
}

.notice-detail__panel-title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(71 85 105);
}

.notice-detail__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgb(15 23 42 / 8%);
}

.notice-detail__panel-extra {
  color: rgb(100 116 139);
  font-size: 12px;
}

.notice-detail__info-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0 0;
}

.notice-detail__info-list div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 8px;
}

.notice-detail__info-list dt {
  color: rgb(100 116 139);
}

.notice-detail__info-list dd {
  margin: 0;
  color: rgb(30 41 59);
  word-break: break-word;
}

.notice-detail__attachments,
.notice-detail__read-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 260px;
  overflow: auto;
  padding-right: 4px;
}

.notice-detail__attachment,
.notice-detail__read-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(15 23 42 / 6%);
}

.notice-detail__attachment:last-child,
.notice-detail__read-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.notice-detail__attachment:first-child,
.notice-detail__read-item:first-child {
  padding-top: 0;
}

.notice-detail__attachment-body,
.notice-detail__read-content {
  min-width: 0;
  flex: 1;
}

.notice-detail__attachment-actions,
.notice-detail__batch-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.notice-detail__attachment-actions {
  flex-shrink: 0;
}

.notice-detail__batch-actions {
  margin-top: 8px;
}

.notice-detail__attachment-name,
.notice-detail__read-name {
  color: rgb(30 41 59);
  font-size: 14px;
  word-break: break-word;
}

.notice-detail__attachment-meta,
.notice-detail__read-time {
  margin-top: 4px;
  color: rgb(100 116 139);
  font-size: 12px;
}

.notice-detail__avatar {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: linear-gradient(135deg, rgb(14 116 144 / 18%), rgb(59 130 246 / 14%));
  color: rgb(14 116 144);
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}

.notice-detail__avatar--muted {
  background: linear-gradient(135deg, rgb(148 163 184 / 18%), rgb(203 213 225 / 20%));
  color: rgb(100 116 139);
}

@media (max-width: 960px) {
  .notice-detail {
    grid-template-columns: minmax(0, 1fr);
  }

  .notice-detail__meta-item--right {
    margin-left: 0;
  }
}
</style>
