<script lang="ts" setup>
import type { SystemPartyFileApi } from '#/api/system/party-file';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createPartyFileCategory,
  getPartyFileCategory,
  updatePartyFileCategory,
} from '#/api/system/party-file';
import { $t } from '#/locales';

import { useCategoryFormSchema } from '../data';

const emit = defineEmits(['success']);
const formData = ref<SystemPartyFileApi.PartyFileCategory>();

const getTitle = computed(() =>
  formData.value?.id ? $t('ui.actionTitle.edit', ['分类']) : $t('ui.actionTitle.create', ['分类']),
);

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    labelWidth: 90,
  },
  layout: 'horizontal',
  schema: useCategoryFormSchema(),
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
      const data = (await formApi.getValues()) as SystemPartyFileApi.PartyFileCategory;
      await (formData.value?.id ? updatePartyFileCategory(data) : createPartyFileCategory(data));
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
      await formApi.resetForm();
      return;
    }
    const data = modalApi.getData<SystemPartyFileApi.PartyFileCategory>();
    if (data?.id) {
      modalApi.lock();
      try {
        formData.value = await getPartyFileCategory(data.id);
        await formApi.setValues(formData.value);
      } finally {
        modalApi.unlock();
      }
      return;
    }
    formData.value = undefined;
    await formApi.setValues({
      parentId: data?.parentId ?? 0,
      sort: 0,
      status: 0,
    });
  },
});
</script>

<template>
  <Modal :title="getTitle" class="w-[520px]">
    <Form class="mx-4" />
  </Modal>
</template>
