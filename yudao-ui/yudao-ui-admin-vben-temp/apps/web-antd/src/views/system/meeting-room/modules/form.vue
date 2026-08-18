<script lang="ts" setup>
import type { SystemMeetingRoomApi } from '#/api/system/meeting-room';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createMeetingRoom,
  getMeetingRoom,
  updateMeetingRoom,
} from '#/api/system/meeting-room';
import { $t } from '#/locales';

import { useFormSchema } from '../data';

const emit = defineEmits(['success']);
const formData = ref<SystemMeetingRoomApi.MeetingRoom>();

const getTitle = computed(() => {
  return formData.value?.id
    ? $t('ui.actionTitle.edit', ['会议室'])
    : $t('ui.actionTitle.create', ['会议室']);
});

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: {
      class: 'w-full',
    },
    formItemClass: 'col-span-2',
    labelWidth: 90,
  },
  layout: 'horizontal',
  schema: useFormSchema(),
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) {
      return;
    }
    modalApi.lock();
    try {
      const data = (await formApi.getValues()) as SystemMeetingRoomApi.MeetingRoom;
      const payload = {
        ...data,
        equipment: Array.isArray(data.equipment)
          ? data.equipment.join(',')
          : data.equipment,
      };
      await (formData.value?.id
        ? updateMeetingRoom(payload)
        : createMeetingRoom(payload));
      await modalApi.close();
      emit('success');
      message.success($t('ui.actionMessage.operationSuccess'));
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      formData.value = undefined;
      return;
    }
    const data = modalApi.getData<SystemMeetingRoomApi.MeetingRoom>();
    if (!data?.id) {
      return;
    }
    modalApi.lock();
    try {
      formData.value = await getMeetingRoom(data.id);
      await formApi.setValues({
        ...formData.value,
        equipment: formData.value.equipment
          ? formData.value.equipment.split(',').filter(Boolean)
          : [],
      });
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal class="w-[640px]" :title="getTitle">
    <Form class="mx-4" />
  </Modal>
</template>
