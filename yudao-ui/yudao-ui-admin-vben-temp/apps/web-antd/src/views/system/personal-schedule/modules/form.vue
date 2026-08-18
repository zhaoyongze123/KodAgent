<script lang="ts" setup>
import type { SystemPersonalScheduleApi } from '#/api/system/personal-schedule';
import type { SystemUserApi } from '#/api/system/user';

import dayjs from 'dayjs';
import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { message, Modal as AntModal } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createPersonalSchedule,
  deletePersonalSchedule,
  getPersonalSchedule,
  updatePersonalSchedule,
} from '#/api/system/personal-schedule';
import { $t } from '#/locales';

import {
  normalizeSchedulePayload,
  type PersonalScheduleFormValues,
  usePersonalScheduleFormSchema,
} from '../data';

const emit = defineEmits(['success']);

interface ModalData {
  schedule?: SystemPersonalScheduleApi.PersonalSchedule;
  initialValues?: Partial<SystemPersonalScheduleApi.PersonalSchedule>;
  userOptions: SystemUserApi.User[];
}

const formData = ref<SystemPersonalScheduleApi.PersonalSchedule>();
const userOptions = ref<Array<{ label: string; value: number }>>([]);

const getTitle = computed(() => {
  return formData.value?.id
    ? $t('ui.actionTitle.edit', ['个人日程'])
    : $t('ui.actionTitle.create', ['个人日程']);
});

function normalizeCreateValues(data?: ModalData): PersonalScheduleFormValues {
  const start = data?.initialValues?.startTime
    ? dayjs(data.initialValues.startTime)
    : dayjs().minute(0).second(0);
  const end = data?.initialValues?.endTime
    ? dayjs(data.initialValues.endTime)
    : start.add(1, 'hour');
  return {
    ...data?.initialValues,
    startTime: start.format('YYYY-MM-DD HH:mm:ss'),
    endTime: end.format('YYYY-MM-DD HH:mm:ss'),
  };
}

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: {
      class: 'w-full',
    },
    formItemClass: 'col-span-2',
    labelWidth: 92,
  },
  layout: 'horizontal',
  schema: [],
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
      const values = (await formApi.getValues()) as PersonalScheduleFormValues;
      const payload = normalizeSchedulePayload(values);
      if (!payload.startTime || !payload.endTime || !dayjs(payload.endTime).isAfter(dayjs(payload.startTime))) {
        message.warning('请填写合法的开始和结束时间');
        return;
      }
      await (formData.value?.id
        ? updatePersonalSchedule(payload)
        : createPersonalSchedule(payload));
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
    const data = modalApi.getData<ModalData>();
    userOptions.value = (data?.userOptions || []).map((item) => ({
      label: item.nickname,
      value: item.id!,
    }));
    formApi.setState({
      schema: usePersonalScheduleFormSchema(userOptions.value),
    });
    if (!data?.schedule?.id) {
      formData.value = undefined;
      await formApi.setValues(normalizeCreateValues(data));
      return;
    }
    modalApi.lock();
    try {
      formData.value = await getPersonalSchedule(data.schedule.id);
      await formApi.setValues(formData.value);
    } finally {
      modalApi.unlock();
    }
  },
});

async function handleDelete() {
  if (!formData.value?.id) {
    return;
  }
  const confirmed = await new Promise<boolean>((resolve) => {
    AntModal.confirm({
      title: '确认删除当前个人日程？',
      content: formData.value?.title || '',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
  if (!confirmed) {
    return;
  }
  modalApi.lock();
  try {
    await deletePersonalSchedule(formData.value.id);
    await modalApi.close();
    emit('success');
    message.success('已删除');
  } finally {
    modalApi.unlock();
  }
}
</script>

<template>
  <Modal class="w-[760px]" :title="getTitle">
    <Form class="mx-4" />
    <template #prepend-footer>
      <a-button v-if="formData?.id" danger @click="handleDelete">
        删除当前日程
      </a-button>
    </template>
  </Modal>
</template>
