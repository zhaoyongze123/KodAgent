<script lang="ts" setup>
import type { SystemPartyFileApi } from '#/api/system/party-file';

import { computed } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createPartyFileKodSource,
  getPartyFileKodSource,
  updatePartyFileKodSource,
} from '#/api/system/party-file';
import { $t } from '#/locales';

import { useKodSourceFormSchema } from '../data';

const emit = defineEmits(['success']);
const [FormRender, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 100,
  },
  layout: 'horizontal',
  schema: useKodSourceFormSchema(),
  showDefaultActions: false,
});

const title = computed(() =>
  modalApi.getData<SystemPartyFileApi.PartyFileKodSource>()?.id
    ? $t('ui.actionTitle.edit', ['目录来源'])
    : $t('ui.actionTitle.create', ['目录来源']),
);

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) {
      return;
    }
    modalApi.lock();
    try {
      const data = (await formApi.getValues()) as SystemPartyFileApi.PartyFileKodSource;
      await (data.id ? updatePartyFileKodSource(data) : createPartyFileKodSource(data));
      await modalApi.close();
      emit('success');
      message.success($t('ui.actionMessage.operationSuccess'));
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen) {
    if (!isOpen) {
      await formApi.resetForm();
      return;
    }
    const data = modalApi.getData<SystemPartyFileApi.PartyFileKodSource>();
    if (!data?.id) {
      await formApi.setValues({ status: 0, isDefault: false });
      return;
    }
    modalApi.lock();
    try {
      await formApi.setValues(await getPartyFileKodSource(data.id));
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal :title="title" class="w-[720px]">
    <div class="mx-4">
      <FormRender />
    </div>
  </Modal>
</template>
