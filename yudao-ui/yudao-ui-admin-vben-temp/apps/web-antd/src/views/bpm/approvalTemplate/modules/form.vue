<script lang="ts" setup>
import type { BpmApprovalTemplateApi } from '#/api/bpm/approvalTemplate';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  getApprovalTemplate,
  updateApprovalTemplate,
} from '#/api/bpm/approvalTemplate';
import { getSimpleProcessDefinitionList } from '#/api/bpm/definition';
import { $t } from '#/locales';

import { buildProcessDefinitionOptions, useFormSchema } from '../data';

const emit = defineEmits(['success']);
const formData = ref<BpmApprovalTemplateApi.ApprovalTemplate>();

const getTitle = computed(() => {
  return formData.value?.id
    ? $t('ui.actionTitle.edit', ['审批模板'])
    : '编辑审批模板';
});

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: {
      class: 'w-full',
    },
    formItemClass: 'col-span-2',
    labelWidth: 100,
  },
  layout: 'horizontal',
  schema: useFormSchema(),
  showDefaultActions: false,
});

async function loadProcessDefinitionOptions() {
  const list = await getSimpleProcessDefinitionList();
  formApi.updateSchema([
    {
      fieldName: 'processDefinitionId',
      componentProps: {
        options: buildProcessDefinitionOptions(list),
      },
    },
  ]);
}

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) {
      return;
    }
    modalApi.lock();
    const data =
      (await formApi.getValues()) as BpmApprovalTemplateApi.ApprovalTemplate;
    try {
      await updateApprovalTemplate(data);
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
    const data = modalApi.getData<BpmApprovalTemplateApi.ApprovalTemplate>();
    if (!data || !data.id) {
      return;
    }
    modalApi.lock();
    try {
      await loadProcessDefinitionOptions();
      formData.value = await getApprovalTemplate(data.id);
      await formApi.setValues(formData.value);
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal :title="getTitle" class="w-2/5">
    <Form class="mx-4" />
  </Modal>
</template>
