<script lang="ts" setup>
import type { SystemNotifyMessageApi } from '#/api/system/notify/message';
import type { SystemNoticeApi } from '#/api/system/notice';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { formatDateTime } from '@vben/utils';

import { Button, Empty, Tag } from 'ant-design-vue';

import { extractNoticeId } from '#/api/system/notify/message';
import { getNotice, getNoticeAttachmentPreviewUrl } from '#/api/system/notice';
import { router } from '#/router';
import { getOaFilePreviewUrl, normalizeOaAssetUrl } from '#/utils';
import { resolveNotificationPresentation } from '#/views/oa-lite/notification-presenter';

const messageData = ref<SystemNotifyMessageApi.NotifyMessage>();
const noticeDetail = ref<SystemNoticeApi.Notice>();

const presentation = computed(() =>
  messageData.value ? resolveNotificationPresentation(messageData.value) : undefined,
);
const isNoticeMessage = computed(() => !!extractNoticeId(messageData.value));

const [ModalApi, modalApi] = useVbenModal({
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      messageData.value = undefined;
      noticeDetail.value = undefined;
      return;
    }
    const data = modalApi.getData<SystemNotifyMessageApi.NotifyMessage>();
    if (!data?.id) {
      return;
    }
    modalApi.lock();
    try {
      messageData.value = data;
      const noticeId = extractNoticeId(data);
      noticeDetail.value = noticeId ? await getNotice(noticeId) : undefined;
    } finally {
      modalApi.unlock();
    }
  },
});

async function handlePreview(attachment: SystemNoticeApi.NoticeAttachment) {
  if (!noticeDetail.value?.id) {
    return;
  }
  const previewWindow = window.open('about:blank', '_blank', 'noopener,noreferrer');
  try {
    const sourceUrl = await getNoticeAttachmentPreviewUrl(noticeDetail.value.id, attachment.id);
    const normalizedUrl = normalizeOaAssetUrl(sourceUrl);
    if (!normalizedUrl) {
      previewWindow?.close();
      return;
    }
    const previewUrl = getOaFilePreviewUrl(normalizedUrl);
    if (previewWindow) {
      previewWindow.location.href = previewUrl;
    } else {
      window.open(previewUrl, '_blank', 'noopener,noreferrer');
    }
  } catch (error) {
    previewWindow?.close();
    throw error;
  }
}

function handleDownload(url?: string) {
  const normalizedUrl = normalizeOaAssetUrl(url);
  if (!normalizedUrl) {
    return;
  }
  window.open(normalizedUrl, '_blank', 'noopener,noreferrer');
}

function handleNotificationAction() {
  const action = presentation.value?.action;
  if (!action) {
    return;
  }
  modalApi.close();
  if (action.to) {
    router.push(action.to);
  } else if (action.url) {
    window.open(action.url, '_blank', 'noopener,noreferrer');
  }
}
</script>

<template>
  <ModalApi
    title="通知详情"
    class="w-[860px]"
    :show-cancel-button="false"
    :show-confirm-button="false"
  >
    <template v-if="messageData">
      <div class="notify-detail">
        <section
          v-if="presentation"
          class="notify-detail__hero"
          :class="`tone-${presentation.tone}`"
        >
          <div class="notify-detail__hero-copy">
            <div class="notify-detail__kicker">{{ presentation.subtitle }}</div>
            <h3>{{ presentation.title }}</h3>
            <p>{{ presentation.preview }}</p>
          </div>
          <Tag class="notify-detail__hero-tag" :class="`tone-${presentation.tone}`">
            {{ presentation.statusLabel }}
          </Tag>
        </section>

        <section class="notify-detail__card">
          <div class="notify-detail__meta-grid">
            <div class="notify-detail__meta-item">
              <span class="label">发送人</span>
              <span>{{ messageData.templateNickname }}</span>
            </div>
            <div class="notify-detail__meta-item">
              <span class="label">阅读状态</span>
              <Tag :color="messageData.readStatus ? 'default' : 'processing'">
                {{ messageData.readStatus ? '已读' : '未读' }}
              </Tag>
            </div>
            <div class="notify-detail__meta-item">
              <span class="label">发送时间</span>
              <span>{{ formatDateTime(messageData.createTime) }}</span>
            </div>
            <div class="notify-detail__meta-item" v-if="messageData.readTime">
              <span class="label">阅读时间</span>
              <span>{{ formatDateTime(messageData.readTime) }}</span>
            </div>
          </div>
        </section>

        <section v-if="presentation" class="notify-detail__card">
          <div class="notify-detail__section-head">关键信息</div>
          <div class="notify-detail__meta-grid">
            <div
              v-for="field in presentation.fields"
              :key="field.label"
              class="notify-detail__meta-item"
            >
              <span class="label">{{ field.label }}</span>
              <span>{{ field.value }}</span>
            </div>
          </div>
        </section>

        <template v-if="isNoticeMessage && noticeDetail">
          <section class="notify-detail__card">
            <div class="notify-detail__notice-head">
              <div>
                <h3>{{ noticeDetail.title }}</h3>
                <p>
                  发布对象：{{ noticeDetail.publishTarget || '全体后台用户' }}
                  <span class="notify-detail__divider"></span>
                  发布时间：{{ formatDateTime(noticeDetail.createTime) }}
                </p>
              </div>
              <Tag :color="noticeDetail.pinned ? 'blue' : 'default'">
                {{ noticeDetail.pinned ? '置顶' : '未置顶' }}
              </Tag>
            </div>
            <div class="notify-detail__content" v-html="noticeDetail.content"></div>

            <section class="notify-detail__attachments">
              <div class="notify-detail__section-head">附件</div>
              <div
                v-if="noticeDetail.attachments && noticeDetail.attachments.length"
                class="notify-detail__attachment-list"
              >
                <div
                  v-for="item in noticeDetail.attachments"
                  :key="item.id"
                  class="notify-detail__attachment-item"
                >
                  <div>
                    <strong>{{ item.name }}</strong>
                    <p>{{ item.type || '未知类型' }}</p>
                  </div>
                  <div class="notify-detail__attachment-actions">
                    <Button type="link" size="small" @click="handlePreview(item)">
                      预览
                    </Button>
                    <Button type="link" size="small" @click="handleDownload(item.url)">
                      下载
                    </Button>
                  </div>
                </div>
              </div>
              <Empty
                v-else
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                description="暂无附件"
              />
            </section>
          </section>
        </template>

        <section v-else-if="presentation" class="notify-detail__card">
          <div class="notify-detail__section-head">{{ presentation.bodyTitle }}</div>
          <div class="notify-detail__plain">
            <p v-for="paragraph in presentation.body" :key="paragraph">
              {{ paragraph }}
            </p>
          </div>
          <div v-if="presentation.action" class="notify-detail__actions">
            <Button type="primary" @click="handleNotificationAction">
              {{ presentation.action.label }}
            </Button>
          </div>
        </section>
      </div>
    </template>
  </ModalApi>
</template>

<style scoped>
.notify-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.notify-detail__hero,
.notify-detail__card {
  border: 1px solid rgb(15 23 42 / 8%);
  background: rgb(255 255 255 / 96%);
}

.notify-detail__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 18px 20px;
  background: linear-gradient(135deg, rgb(37 99 235 / 8%), rgb(255 255 255 / 98%));
}

.notify-detail__hero.tone-success {
  background: linear-gradient(135deg, rgb(34 197 94 / 10%), rgb(255 255 255 / 98%));
}

.notify-detail__hero.tone-warning {
  background: linear-gradient(135deg, rgb(245 158 11 / 12%), rgb(255 255 255 / 98%));
}

.notify-detail__hero.tone-danger {
  background: linear-gradient(135deg, rgb(239 68 68 / 10%), rgb(255 255 255 / 98%));
}

.notify-detail__hero-copy h3,
.notify-detail__notice-head h3 {
  margin: 0;
  color: rgb(15 23 42);
  font-size: 24px;
  line-height: 1.32;
}

.notify-detail__hero-copy p {
  margin: 10px 0 0;
  max-width: 68ch;
  color: rgb(71 85 105);
  line-height: 1.72;
}

.notify-detail__kicker {
  color: rgb(100 116 139);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.notify-detail__hero-tag {
  font-weight: 600;
}

.notify-detail__hero-tag.tone-success {
  color: rgb(21 128 61);
  background: rgb(34 197 94 / 12%);
  border-color: rgb(34 197 94 / 22%);
}

.notify-detail__hero-tag.tone-warning {
  color: rgb(180 83 9);
  background: rgb(245 158 11 / 14%);
  border-color: rgb(245 158 11 / 24%);
}

.notify-detail__hero-tag.tone-danger {
  color: rgb(185 28 28);
  background: rgb(239 68 68 / 12%);
  border-color: rgb(239 68 68 / 22%);
}

.notify-detail__card {
  padding: 18px 20px;
}

.notify-detail__meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
}

.notify-detail__meta-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  color: rgb(15 23 42);
}

.notify-detail__meta-item .label,
.notify-detail__section-head {
  color: rgb(100 116 139);
  font-size: 12px;
  font-weight: 600;
}

.notify-detail__section-head {
  margin-bottom: 14px;
}

.notify-detail__notice-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgb(15 23 42 / 10%);
}

.notify-detail__notice-head p {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0 0;
  color: rgb(100 116 139);
  font-size: 13px;
  flex-wrap: wrap;
}

.notify-detail__divider {
  width: 1px;
  height: 12px;
  background: rgb(15 23 42 / 12%);
}

.notify-detail__content {
  margin-top: 18px;
  color: rgb(15 23 42);
  line-height: 1.85;
}

.notify-detail__attachments {
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid rgb(15 23 42 / 10%);
}

.notify-detail__attachment-list {
  display: flex;
  flex-direction: column;
}

.notify-detail__attachment-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid rgb(15 23 42 / 8%);
}

.notify-detail__attachment-item strong {
  color: rgb(15 23 42);
}

.notify-detail__attachment-item p {
  margin: 4px 0 0;
  color: rgb(100 116 139);
  font-size: 12px;
}

.notify-detail__attachment-actions,
.notify-detail__actions {
  display: flex;
  gap: 8px;
}

.notify-detail__plain p {
  margin: 0;
  color: rgb(15 23 42);
  line-height: 1.82;
}

.notify-detail__plain p + p {
  margin-top: 10px;
}

.notify-detail__actions {
  justify-content: flex-end;
  margin-top: 18px;
}

@media (max-width: 768px) {
  .notify-detail__hero {
    flex-direction: column;
  }

  .notify-detail__meta-grid {
    grid-template-columns: 1fr;
  }

  .notify-detail__actions :deep(.ant-btn) {
    width: 100%;
  }
}
</style>
