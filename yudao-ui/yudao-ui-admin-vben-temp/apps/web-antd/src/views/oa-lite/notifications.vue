<script lang="ts" setup>
import type { SystemNotifyMessageApi } from '#/api/system/notify/message';
import type { SystemNoticeApi } from '#/api/system/notice';

import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import { formatDateTime } from '@vben/utils';

import { Button, Empty, message, Modal, Pagination, Spin, Tag } from 'ant-design-vue';

import {
  extractNoticeId,
  getMyNotifyMessagePage,
  updateAllNotifyMessageRead,
  updateNotifyMessageRead,
} from '#/api/system/notify/message';
import { getNotice } from '#/api/system/notice';
import { router } from '#/router';
import {
  resolveNotificationPresentation,
  resolveNotificationPreview,
} from '#/views/oa-lite/notification-presenter';

type ReadFilter = 'all' | 'read' | 'unread';
const OA_LITE_NOTICE_PUSH_EVENT = 'oa-lite-notice-push';
const route = useRoute();

const loading = ref(false);
const selectedMessage = ref<null | SystemNotifyMessageApi.NotifyMessage>(null);
const selectedNotice = ref<SystemNoticeApi.Notice>();
const readFilter = ref<ReadFilter>('all');
const messages = ref<SystemNotifyMessageApi.NotifyMessage[]>([]);

const pageState = reactive({
  pageNo: 1,
  pageSize: 10,
  total: 0,
});

const readFilterOptions: Array<{ key: ReadFilter; label: string }> = [
  { key: 'all', label: '全部消息' },
  { key: 'unread', label: '未读' },
  { key: 'read', label: '已读' },
];

const unreadCount = computed(
  () => messages.value.filter((item) => !item.readStatus).length,
);
const selectedPresentation = computed(() =>
  selectedMessage.value ? resolveNotificationPresentation(selectedMessage.value) : undefined,
);

function resolveReadStatus(filter: ReadFilter) {
  if (filter === 'all') {
    return undefined;
  }
  return filter === 'read';
}

async function loadMessages() {
  loading.value = true;
  try {
    const pageResult = await getMyNotifyMessagePage({
      pageNo: pageState.pageNo,
      pageSize: pageState.pageSize,
      readStatus: resolveReadStatus(readFilter.value),
    });
    messages.value = pageResult.list;
    pageState.total = pageResult.total;
    await tryOpenMessageFromRoute();
  } finally {
    loading.value = false;
  }
}

function resolveRouteMessageId() {
  const raw = route.query.messageId;
  if (Array.isArray(raw)) {
    return Number(raw[0]);
  }
  return raw ? Number(raw) : undefined;
}

async function tryOpenMessageFromRoute() {
  const routeMessageId = resolveRouteMessageId();
  if (!routeMessageId) {
    return;
  }
  const target = messages.value.find((item) => item.id === routeMessageId);
  if (!target) {
    return;
  }
  await handleViewDetail(target);
  router.replace({ path: route.path, query: {} });
}

async function handleFilterChange(filter: ReadFilter) {
  if (readFilter.value === filter) {
    return;
  }
  readFilter.value = filter;
  pageState.pageNo = 1;
  await loadMessages();
}

async function handlePageChange(pageNo: number, pageSize: number) {
  pageState.pageNo = pageNo;
  pageState.pageSize = pageSize;
  await loadMessages();
}

function handleBack() {
  router.push({ name: 'OALite' });
}

async function handleViewDetail(item: SystemNotifyMessageApi.NotifyMessage) {
  if (!item.readStatus) {
    await updateNotifyMessageRead([item.id]);
    item.readStatus = true;
    item.readTime = new Date() as any;
  }
  selectedMessage.value = item;
  selectedNotice.value = undefined;
  const noticeId = extractNoticeId(item);
  if (!noticeId) {
    return;
  }
  selectedNotice.value = await getNotice(noticeId);
}

async function handleMarkRead(item: SystemNotifyMessageApi.NotifyMessage) {
  if (item.readStatus) {
    await handleViewDetail(item);
    return;
  }
  const hideLoading = message.loading({
    content: '正在标记已读...',
    duration: 0,
  });
  try {
    await updateNotifyMessageRead([item.id]);
    message.success('标记已读成功');
    await loadMessages();
    selectedMessage.value = {
      ...item,
      readStatus: true,
      readTime: new Date(),
    };
    const noticeId = extractNoticeId(item);
    selectedNotice.value = noticeId ? await getNotice(noticeId) : undefined;
  } finally {
    hideLoading();
  }
}

async function handleMarkAllRead() {
  const hideLoading = message.loading({
    content: '正在标记全部已读...',
    duration: 0,
  });
  try {
    await updateAllNotifyMessageRead();
    message.success('全部标记已读成功');
    await loadMessages();
  } finally {
    hideLoading();
  }
}

function handleOpenNotificationAction() {
  const action = selectedPresentation.value?.action;
  if (!action) {
    return;
  }
  if (action.to) {
    router.push(action.to);
  } else if (action.url) {
    window.open(action.url, '_blank', 'noopener,noreferrer');
  }
}

onMounted(() => {
  loadMessages();
  if (typeof window !== 'undefined') {
    window.addEventListener(OA_LITE_NOTICE_PUSH_EVENT, loadMessages);
  }
});

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener(OA_LITE_NOTICE_PUSH_EVENT, loadMessages);
  }
});
</script>

<template>
  <div class="oa-notify-page">
    <div class="oa-notify-shell">
      <section class="oa-notify-hero">
        <div class="oa-notify-hero-main">
          <div class="oa-notify-eyebrow">Notifications</div>
          <h1 class="oa-notify-heading">消息中心</h1>
        </div>
        <div class="oa-notify-hero-summary">
          <span>未读 {{ unreadCount }}</span>
          <span class="oa-notify-summary-divider"></span>
          <span>历史 {{ pageState.total }}</span>
        </div>
      </section>

      <section class="oa-notify-section">
        <div class="oa-notify-section-head">
          <div>
            <h3 class="oa-notify-section-title">消息筛选与处理</h3>
          </div>
          <div class="oa-notify-header-actions">
            <Button @click="handleBack">返回 OA</Button>
            <Button type="primary" @click="handleMarkAllRead">全部标记已读</Button>
          </div>
        </div>
        <div class="oa-notify-section-body">
          <section class="oa-notify-toolbar">
            <div class="oa-notify-filters">
              <button
                v-for="option in readFilterOptions"
                :key="option.key"
                class="oa-notify-filter"
                :class="{ active: readFilter === option.key }"
                type="button"
                @click="handleFilterChange(option.key)"
              >
                {{ option.label }}
              </button>
            </div>
            <div class="oa-notify-summary">
              <span>当前页未读 {{ unreadCount }} 条</span>
              <span class="oa-notify-summary-divider"></span>
              <span>共 {{ pageState.total }} 条历史消息</span>
            </div>
          </section>
        </div>
      </section>

      <section class="oa-notify-section oa-notify-list-panel">
        <div class="oa-notify-section-head">
          <div>
            <h3 class="oa-notify-section-title">消息列表</h3>
          </div>
        </div>
        <div class="oa-notify-section-body">
          <section class="oa-notify-list-shell">
            <div class="oa-notify-list-head">
              <span class="sender">发送人</span>
              <span class="content">消息内容</span>
              <span class="time">时间</span>
              <span class="status">状态</span>
              <span class="action">操作</span>
            </div>
            <Spin :spinning="loading">
              <template v-if="messages.length > 0">
                <article
                  v-for="item in messages"
                  :key="item.id"
                  class="oa-notify-item"
                  :class="{ unread: !item.readStatus }"
                >
                  <button
                    class="oa-notify-item-main"
                    type="button"
                      @click="handleViewDetail(item)"
                    >
                      <div class="oa-notify-item-sender">
                      <span>{{ item.templateNickname }}</span>
                      <span v-if="!item.readStatus" class="oa-notify-inline-mark">未读</span>
                      </div>
                    <div class="oa-notify-item-content">
                      <div class="oa-notify-item-subject">
                        {{ resolveNotificationPreview(item) }}
                      </div>
                    </div>
                    <div class="oa-notify-item-time">
                      <span>{{ formatDateTime(item.createTime) }}</span>
                      <span v-if="item.readTime" class="oa-notify-read-time">
                        读于 {{ formatDateTime(item.readTime) }}
                      </span>
                    </div>
                    <div class="oa-notify-item-status">
                      <Tag
                        :color="item.readStatus ? 'default' : 'processing'"
                        class="oa-notify-status-tag"
                        :class="{ read: item.readStatus, unread: !item.readStatus }"
                      >
                        {{ item.readStatus ? '已读' : '未读' }}
                      </Tag>
                    </div>
                  </button>
                  <div class="oa-notify-item-actions">
                    <Button type="link" @click="handleViewDetail(item)">查看详情</Button>
                    <Button
                      v-if="!item.readStatus"
                      type="link"
                      @click="handleMarkRead(item)"
                    >
                      标记已读
                    </Button>
                  </div>
                </article>
              </template>
              <Empty v-else description="暂无历史消息" />
            </Spin>
          </section>

          <div class="oa-notify-pagination">
            <Pagination
              :current="pageState.pageNo"
              :page-size="pageState.pageSize"
              :total="pageState.total"
              :show-size-changer="true"
              :show-total="(total) => `共 ${total} 条`"
              @change="handlePageChange"
            />
          </div>
        </div>
      </section>
    </div>

    <Modal
      :open="selectedMessage !== null"
      title="通知详情"
      :footer="null"
      wrap-class-name="oa-notify-modal"
      @cancel="
        () => {
          selectedMessage = null;
          selectedNotice = undefined;
        }
      "
    >
      <template v-if="selectedMessage">
        <div class="oa-notify-detail">
          <section
            v-if="selectedPresentation"
            class="oa-notify-detail-hero"
            :class="`tone-${selectedPresentation.tone}`"
          >
            <div class="oa-notify-detail-hero-copy">
              <div class="oa-notify-detail-kicker">{{ selectedPresentation.subtitle }}</div>
              <h3 class="oa-notify-detail-title">{{ selectedPresentation.title }}</h3>
              <p class="oa-notify-detail-summary">{{ selectedPresentation.preview }}</p>
            </div>
            <Tag
              class="oa-notify-status-tag oa-notify-status-tag--hero"
              :class="[
                selectedMessage.readStatus ? 'read' : 'unread',
                `tone-${selectedPresentation.tone}`,
              ]"
            >
              {{ selectedPresentation.statusLabel }}
            </Tag>
          </section>

          <section class="oa-notify-detail-meta-card">
            <div class="oa-notify-detail-meta-grid">
              <div class="oa-notify-detail-meta-item">
                <span class="label">发送人</span>
                <span>{{ selectedMessage.templateNickname }}</span>
              </div>
              <div class="oa-notify-detail-meta-item">
                <span class="label">阅读状态</span>
                <Tag
                  :color="selectedMessage.readStatus ? 'default' : 'processing'"
                  class="oa-notify-status-tag"
                  :class="{
                    read: selectedMessage.readStatus,
                    unread: !selectedMessage.readStatus,
                  }"
                >
                  {{ selectedMessage.readStatus ? '已读' : '未读' }}
                </Tag>
              </div>
              <div class="oa-notify-detail-meta-item">
                <span class="label">发送时间</span>
                <span>{{ formatDateTime(selectedMessage.createTime) }}</span>
              </div>
              <div class="oa-notify-detail-meta-item" v-if="selectedMessage.readTime">
                <span class="label">阅读时间</span>
                <span>{{ formatDateTime(selectedMessage.readTime) }}</span>
              </div>
            </div>
          </section>

          <section v-if="selectedPresentation" class="oa-notify-detail-brief">
            <div class="oa-notify-detail-brief-head">关键信息</div>
            <div class="oa-notify-detail-brief-grid">
              <div
                v-for="field in selectedPresentation.fields"
                :key="field.label"
                class="oa-notify-detail-brief-item"
              >
                <span class="label">{{ field.label }}</span>
                <span class="value">{{ field.value }}</span>
              </div>
            </div>
          </section>
          <template v-if="selectedNotice">
            <div class="oa-notify-detail-notice-head">
              <div>
                <h3>{{ selectedNotice.title }}</h3>
                <p>
                  发布对象：{{ selectedNotice.publishTarget || '全体后台用户' }}
                  <span class="oa-notify-detail-divider"></span>
                  发布时间：{{ formatDateTime(selectedNotice.createTime) }}
                </p>
              </div>
              <Tag :color="selectedNotice.pinned ? 'blue' : 'default'">
                {{ selectedNotice.pinned ? '置顶' : '未置顶' }}
              </Tag>
            </div>
            <div class="oa-notify-detail-content" v-html="selectedNotice.content"></div>
            <section class="oa-notify-detail-attachments">
              <div class="oa-notify-detail-attachments-head">附件</div>
              <div
                v-if="selectedNotice.attachments && selectedNotice.attachments.length"
                class="oa-notify-detail-attachment-list"
              >
                <div
                  v-for="attachment in selectedNotice.attachments"
                  :key="attachment.id"
                  class="oa-notify-detail-attachment-item"
                >
                  <div class="oa-notify-detail-attachment-meta">
                    <strong>{{ attachment.name }}</strong>
                    <span>{{ attachment.type || '未知类型' }}</span>
                  </div>
                  <div class="oa-notify-detail-attachment-actions">
                    <Button
                      type="link"
                      size="small"
                      @click="window.open(attachment.url, '_blank', 'noopener,noreferrer')"
                    >
                      预览
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      @click="window.open(attachment.url, '_blank', 'noopener,noreferrer')"
                    >
                      下载
                    </Button>
                  </div>
                </div>
              </div>
              <Empty v-else description="暂无附件" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
            </section>
          </template>
          <section v-else-if="selectedPresentation" class="oa-notify-detail-content-shell">
            <div class="oa-notify-detail-content-head">
              {{ selectedPresentation.bodyTitle }}
            </div>
            <div class="oa-notify-detail-content oa-notify-detail-content--plain">
              <p
                v-for="paragraph in selectedPresentation.body"
                :key="paragraph"
                class="oa-notify-detail-paragraph"
              >
                {{ paragraph }}
              </p>
            </div>
            <div v-if="selectedPresentation.action" class="oa-notify-detail-actions">
              <Button type="primary" @click="handleOpenNotificationAction">
                {{ selectedPresentation.action.label }}
              </Button>
            </div>
          </section>
        </div>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.oa-notify-page {
  min-height: 100%;
  padding: 0 clamp(16px, 2vw, 28px) 24px;
  background: transparent;
}

.oa-notify-shell {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.oa-notify-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 0 18px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-notify-hero-main {
  min-width: 0;
}

.oa-notify-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.oa-notify-heading {
  margin: 8px 0 0;
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

.oa-notify-hero-summary {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-notify-section {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.oa-notify-section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
}

.oa-notify-section-title {
  margin: 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-notify-section-body {
  min-width: 0;
  padding-top: 12px;
}

.oa-notify-header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.oa-notify-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: end;
  justify-content: space-between;
  padding: 0 0 2px;
  border: 0;
  background: transparent;
}

.oa-notify-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.oa-notify-filter {
  padding: 8px 0;
  border: 1px solid var(--oa-shell-border);
  border-width: 0 0 1px;
  border-radius: 0;
  color: var(--oa-ink-soft);
  background: transparent;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease;
  font-size: 13px;
  min-width: 58px;
}

.oa-notify-filter.active {
  border-color: var(--oa-accent);
  color: var(--oa-accent);
  background: transparent;
}

.oa-notify-summary {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-notify-summary-divider {
  width: 1px;
  height: 12px;
  background: var(--oa-shell-border);
}

.oa-notify-list-shell {
  overflow-x: auto;
  overflow-y: visible;
  border-radius: 0;
  border-top: 1px solid var(--oa-shell-border);
  border-bottom: 0;
  background: transparent;
}

.oa-notify-list-head {
  display: grid;
  grid-template-columns: 180px minmax(0, 1.8fr) 220px 90px 120px;
  gap: 16px;
  align-items: center;
  padding: 8px 0 12px;
  border-bottom: 1px solid var(--oa-shell-border);
  color: var(--oa-ink-soft);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: transparent;
}

.oa-notify-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 16px;
  align-items: center;
  padding: 0;
  border-bottom: 1px solid var(--oa-shell-border);
  transition: border-color 0.2s ease;
  position: relative;
}

.oa-notify-item:hover {
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 22%, var(--oa-shell-border));
}

.oa-notify-item:last-child {
  border-bottom: none;
}

.oa-notify-item-main {
  display: grid;
  grid-template-columns: 180px minmax(0, 1.8fr) 220px 90px;
  gap: 16px;
  align-items: center;
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  padding: 16px 0;
  cursor: pointer;
  text-align: left;
}

.oa-notify-item.unread::before {
  content: '';
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 2px;
  background: var(--oa-accent);
}

.oa-notify-item.unread .oa-notify-item-content {
  color: var(--oa-ink);
}

.oa-notify-item-sender {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--oa-ink);
  font-size: 14px;
  font-weight: 600;
}

.oa-notify-inline-mark {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-accent) 34%, var(--oa-shell-border));
  color: var(--oa-accent);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.oa-notify-item-content {
  min-width: 0;
  color: var(--oa-ink-soft);
  font-size: 14px;
  line-height: 1.55;
}

.oa-notify-item-subject {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.oa-notify-item-time {
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-notify-read-time {
  color: var(--oa-ink-faint);
  font-size: 12px;
}

.oa-notify-item-status {
  display: flex;
  justify-content: flex-start;
}

.oa-notify-item-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  justify-content: center;
  min-width: 0;
  padding-right: 4px;
}

.oa-notify-item-actions :deep(.ant-btn) {
  padding-inline: 0;
}

@media (max-width: 1100px) {
  .oa-notify-list-head {
    grid-template-columns: 160px minmax(0, 1.4fr) 180px 80px 96px;
    gap: 12px;
  }

  .oa-notify-item {
    grid-template-columns: minmax(0, 1fr) 96px;
    gap: 12px;
  }

  .oa-notify-item-main {
    grid-template-columns: 160px minmax(0, 1.4fr) 180px 80px;
    gap: 12px;
  }
}

@media (max-width: 860px) {
  .oa-notify-list-head {
    display: none;
  }

  .oa-notify-item {
    grid-template-columns: 1fr;
    gap: 0;
    padding: 14px 0;
  }

  .oa-notify-item-main {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 0;
  }

  .oa-notify-item-actions {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 12px;
    padding-top: 10px;
    padding-right: 0;
    border-top: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, transparent);
  }

  .oa-notify-item-status,
  .oa-notify-item-time {
    justify-content: flex-start;
  }
}

.oa-notify-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
  padding-top: 2px;
}

.oa-notify-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.oa-notify-detail-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, transparent);
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--oa-accent) 8%, white),
      color-mix(in srgb, var(--oa-accent) 2%, white)
    );
}

.oa-notify-detail-hero.tone-success {
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, #16a34a 10%, white),
      color-mix(in srgb, #16a34a 2%, white)
    );
}

.oa-notify-detail-hero.tone-warning {
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, #d97706 12%, white),
      color-mix(in srgb, #d97706 2%, white)
    );
}

.oa-notify-detail-hero.tone-danger {
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, #dc2626 10%, white),
      color-mix(in srgb, #dc2626 2%, white)
    );
}

.oa-notify-detail-hero-copy {
  min-width: 0;
}

.oa-notify-detail-kicker {
  color: var(--oa-ink-soft);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.oa-notify-detail-title {
  margin: 8px 0 0;
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  line-height: 1.32;
}

.oa-notify-detail-summary {
  margin: 10px 0 0;
  max-width: 68ch;
  color: var(--oa-ink-soft);
  font-size: 14px;
  line-height: 1.7;
}

.oa-notify-detail-meta-card,
.oa-notify-detail-brief,
.oa-notify-detail-content-shell {
  padding: 18px 20px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, transparent);
  background: color-mix(in srgb, white 94%, var(--oa-accent) 1%);
}

.oa-notify-detail-meta-grid,
.oa-notify-detail-brief-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
}

.oa-notify-detail-meta-item,
.oa-notify-detail-brief-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  color: var(--oa-ink);
}

.oa-notify-detail-meta-item .label,
.oa-notify-detail-brief-item .label {
  color: var(--oa-ink-soft);
  font-size: 12px;
  font-weight: 600;
}

.oa-notify-detail-brief-head,
.oa-notify-detail-content-head {
  margin-bottom: 14px;
  color: var(--oa-ink);
  font-size: 14px;
  font-weight: 600;
}

.oa-notify-detail-brief-item .value {
  color: var(--oa-ink);
  font-size: 15px;
  line-height: 1.6;
}

.oa-notify-detail-content {
  padding: 0;
  border: 0;
  color: var(--oa-ink);
  line-height: 1.8;
  background: transparent;
}

.oa-notify-detail-content--plain {
  white-space: normal;
}

.oa-notify-detail-paragraph {
  margin: 0;
}

.oa-notify-detail-paragraph + .oa-notify-detail-paragraph {
  margin-top: 10px;
}

.oa-notify-detail-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.oa-notify-detail-notice-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-notify-detail-notice-head h3 {
  margin: 0;
  color: var(--oa-ink);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.35;
}

.oa-notify-detail-notice-head p {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 0;
  color: var(--oa-ink-soft);
  font-size: 13px;
  flex-wrap: wrap;
}

.oa-notify-detail-divider {
  width: 1px;
  height: 12px;
  background: var(--oa-shell-border);
}

.oa-notify-detail-attachments {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--oa-shell-border);
}

.oa-notify-detail-attachments-head {
  color: var(--oa-ink);
  font-size: 13px;
  font-weight: 600;
}

.oa-notify-detail-attachment-list {
  display: flex;
  flex-direction: column;
}

.oa-notify-detail-attachment-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-notify-detail-attachment-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.oa-notify-detail-attachment-meta strong {
  color: var(--oa-ink);
  font-size: 14px;
}

.oa-notify-detail-attachment-meta span {
  color: var(--oa-ink-soft);
  font-size: 12px;
}

.oa-notify-detail-attachment-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.oa-notify-modal .ant-modal-content) {
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, transparent);
  box-shadow: 0 18px 44px rgb(15 23 42 / 10%);
}

:deep(.oa-notify-modal .ant-modal-body) {
  padding-top: 18px;
}

:deep(.oa-notify-modal .ant-modal-header) {
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, transparent);
  background: transparent;
}

:deep(.oa-notify-modal .ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
}

:deep(.oa-notify-status-tag.read) {
  border-color: color-mix(in srgb, var(--oa-ink-faint) 24%, var(--oa-shell-border)) !important;
  color: var(--oa-ink-soft) !important;
  background: transparent !important;
}

:deep(.oa-notify-status-tag.unread) {
  border-color: color-mix(in srgb, var(--oa-accent) 34%, var(--oa-shell-border)) !important;
  color: var(--oa-accent) !important;
  background: transparent !important;
}

:deep(.oa-notify-status-tag--hero) {
  padding-inline: 10px !important;
  padding-block: 3px !important;
  font-weight: 600;
}

:deep(.oa-notify-status-tag--hero.tone-success) {
  border-color: color-mix(in srgb, #16a34a 28%, transparent) !important;
  color: #15803d !important;
  background: color-mix(in srgb, #16a34a 10%, white) !important;
}

:deep(.oa-notify-status-tag--hero.tone-warning) {
  border-color: color-mix(in srgb, #d97706 30%, transparent) !important;
  color: #b45309 !important;
  background: color-mix(in srgb, #d97706 11%, white) !important;
}

:deep(.oa-notify-status-tag--hero.tone-danger) {
  border-color: color-mix(in srgb, #dc2626 26%, transparent) !important;
  color: #b91c1c !important;
  background: color-mix(in srgb, #dc2626 9%, white) !important;
}

@media (max-width: 768px) {
  .oa-notify-page {
    padding: 0 16px 20px;
  }

  .oa-notify-hero,
  .oa-notify-section-head,
  .oa-notify-toolbar {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }

  .oa-notify-header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .oa-notify-list-head {
    display: none;
  }

  .oa-notify-item {
    padding: 0 16px 16px;
  }

  .oa-notify-item-main {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 16px 0 10px;
  }

  .oa-notify-item-status {
    justify-content: flex-start;
  }

  .oa-notify-item-actions {
    position: static;
    justify-content: flex-start;
    transform: none;
  }

  .oa-notify-summary {
    flex-wrap: wrap;
  }

  .oa-notify-pagination {
    justify-content: center;
  }

  .oa-notify-detail-hero,
  .oa-notify-detail-meta-grid,
  .oa-notify-detail-brief-grid {
    grid-template-columns: 1fr;
  }

  .oa-notify-detail-hero {
    flex-direction: column;
  }

  .oa-notify-detail-actions {
    justify-content: stretch;
  }

  .oa-notify-detail-actions :deep(.ant-btn) {
    width: 100%;
  }
}
</style>
