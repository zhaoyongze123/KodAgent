<script lang="ts" setup>
import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemPartyFileApi } from '#/api/system/party-file';
import type { SystemRoleApi } from '#/api/system/role';
import type { SystemUserApi } from '#/api/system/user';

import dayjs from 'dayjs';
import { computed, onMounted, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Button, Divider, Input, Modal as AModal, Select, Table, TreeSelect, message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createPartyFile,
  getPartyFile,
  getPartyFileKodFiles,
  getPartyFileKodFolderTree,
  getSimplePartyFileKodSourceList,
  selectPartyFileKodFiles,
  uploadPartyFileAttachment,
  updatePartyFile,
} from '#/api/system/party-file';
import { $t } from '#/locales';

import { buildTargetSelectOptions, usePartyFileFormSchema } from '../data';

type TargetRow = {
  targetType: number;
  targetId?: number;
};

const emit = defineEmits(['success']);
const formData = ref<SystemPartyFileApi.PartyFile>();
const attachmentFiles = ref<Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>>>([]);
const targets = ref<TargetRow[]>([{ targetType: 1 }]);
const users = ref<SystemUserApi.User[]>([]);
const depts = ref<SystemDeptApi.Dept[]>([]);
const roles = ref<SystemRoleApi.Role[]>([]);
const kodSourceOptions = ref<Array<{ label: string; value: number }>>([]);
const kodFolderTree = ref<SystemPartyFileApi.PartyFileKodFolder[]>([]);
const storageTypeValue = ref<number>(1);
const kodSourceIdValue = ref<number>();
const kodFolderPathValue = ref<string>();
const kodFileModalOpen = ref(false);
const kodFileLoading = ref(false);
const kodFileList = ref<SystemPartyFileApi.PartyFileKodFile[]>([]);
const selectedKodFilePaths = ref<string[]>([]);
const selectedKodFiles = ref<SystemPartyFileApi.PartyFileKodFile[]>([]);

const kodFileColumns = [
  { title: '文件名', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '大小', dataIndex: 'size', key: 'size', width: 120 },
  { title: '路径', dataIndex: 'pathDisplay', key: 'pathDisplay', ellipsis: true },
];

function normalizeAttachmentList(
  value?: Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>> | string | string[],
): Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>> {
  if (!value) {
    return [];
  }
  if (!Array.isArray(value)) {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => ({ url: item, name: item.slice(Math.max(0, item.lastIndexOf('/') + 1)) }));
  }
  if (value.every((item) => typeof item === 'string')) {
    return (value as string[])
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => ({ url: item, name: item.slice(Math.max(0, item.lastIndexOf('/') + 1)) }));
  }
  return value as Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>>;
}

function resolveAttachmentFileIds(value: Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>>) {
  const files = normalizeAttachmentList(value);
  if (files.length === 0) {
    return '';
  }
  return files
    .map((item) => Number((item as Record<string, any>).id))
    .filter((id): id is number => typeof id === 'number')
    .join(',');
}

function mergeAttachmentFiles(
  current: Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>>,
  incoming: SystemPartyFileApi.PartyFileAttachment[],
) {
  const merged = [...normalizeAttachmentList(current)];
  for (const item of incoming) {
    if (!merged.some((currentItem) => Number((currentItem as Record<string, any>).id) === Number(item.id))) {
      merged.push(item as Record<string, any>);
    }
  }
  return merged;
}

function appendTarget() {
  targets.value.push({ targetType: 2 });
}

function removeTarget(index: number) {
  targets.value.splice(index, 1);
  if (targets.value.length === 0) {
    targets.value = [{ targetType: 1 }];
  }
}

function handleTargetTypeChange(index: number, value: number) {
  targets.value[index] = { targetType: value };
  if (value === 1) {
    targets.value = [{ targetType: 1 }];
  }
}

function getTargetOptions(targetType: number) {
  if (targetType === 2) {
    return users.value.map((item) => ({ label: item.nickname, value: item.id }));
  }
  if (targetType === 4) {
    return roles.value.map((item) => ({ label: item.name, value: item.id }));
  }
  return [];
}

const getTitle = computed(() =>
  formData.value?.id ? $t('ui.actionTitle.edit', ['党务文件']) : $t('ui.actionTitle.create', ['党务文件']),
);

function handleKodFileSelectionChange(
  keys: Array<number | string>,
  rows: SystemPartyFileApi.PartyFileKodFile[],
) {
  selectedKodFilePaths.value = keys as string[];
  selectedKodFiles.value = rows;
}

const [FormRender, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 90,
  },
  layout: 'horizontal',
  schema: usePartyFileFormSchema(),
  showDefaultActions: false,
});

formApi.updateSchema([
  {
    fieldName: 'attachmentFileIds',
    componentProps: (values: Record<string, any>) => {
      const isKodStorage = Number(values.storageType || 1) === 2;
      const isBlocked = isKodStorage && (!values.kodSourceId || !values.kodFolderPath);
      return {
        maxNumber: 10,
        multiple: true,
        showDescription: true,
        uploadText: '本地文件',
        resultField: 'id',
        modelValue: attachmentFiles.value as any,
        disabled: isBlocked,
        extraActions: isKodStorage
          ? [
              {
                key: 'select-kod-file',
                label: '选择可道云文件',
                disabled: isBlocked,
                onClick: () => {
                  void openKodFileModal();
                },
              },
            ]
          : [],
        api: async (file: File) => {
          const currentValues = (await formApi.getValues()) as SystemPartyFileApi.PartyFile;
          if (
            Number(currentValues.storageType || 1) === 2
            && (!currentValues.kodSourceId || !currentValues.kodFolderPath)
          ) {
            message.error('请先选择可道云目录来源和目标目录，再上传本地文件');
            throw new Error('可道云目录未选择');
          }
          return await uploadPartyFileAttachment({
            file,
            storageType: Number(currentValues.storageType || 1),
            kodFolderPath: currentValues.kodFolderPath,
            kodSourceId: currentValues.kodSourceId,
          });
        },
        'onUpdate:modelValue': (value: Array<SystemPartyFileApi.PartyFileAttachment | Record<string, any>>) => {
          attachmentFiles.value = normalizeAttachmentList(value);
        },
      };
    },
  },
  {
    fieldName: 'storageType',
    componentProps: {
      onChange: (value: number) => {
        storageTypeValue.value = Number(value || 1);
        if (storageTypeValue.value !== 2) {
          kodFileModalOpen.value = false;
        }
      },
    },
  },
  {
    fieldName: 'kodSourceId',
    componentProps: {
      options: kodSourceOptions.value,
      onChange: async (value: number) => {
        kodSourceIdValue.value = value;
        await handleKodSourceChange(value);
      },
    },
  },
  {
    fieldName: 'kodFolderPath',
    componentProps: {
      treeData: kodFolderTree.value,
      fieldNames: { children: 'children', label: 'title', value: 'value' },
      treeNodeFilterProp: 'title',
      showSearch: true,
      onChange: (value: string, _label: unknown, extra: { triggerNode?: { title?: string } }) => {
        kodFolderPathValue.value = value;
        void formApi.setFieldValue('kodFolderName', extra?.triggerNode?.title || '');
      },
    },
  },
]);

async function openKodFileModal() {
  const values = (await formApi.getValues()) as SystemPartyFileApi.PartyFile;
  if (Number(values.storageType || 1) !== 2) {
    message.error('当前存储方式不是可道云目录');
    return;
  }
  if (!values.kodSourceId || !values.kodFolderPath) {
    message.error('请先选择可道云目录来源和目标目录');
    return;
  }
  kodFileLoading.value = true;
  try {
    kodFileList.value = await getPartyFileKodFiles({
      kodSourceId: Number(values.kodSourceId),
      kodFolderPath: values.kodFolderPath,
    });
    selectedKodFilePaths.value = [];
    selectedKodFiles.value = [];
    kodFileModalOpen.value = true;
  } finally {
    kodFileLoading.value = false;
  }
}

async function confirmKodFileSelection() {
  const values = (await formApi.getValues()) as SystemPartyFileApi.PartyFile;
  if (!selectedKodFiles.value.length) {
    message.error('请至少选择一个可道云文件');
    return;
  }
  kodFileLoading.value = true;
  try {
    const attachments = await selectPartyFileKodFiles({
      kodSourceId: Number(values.kodSourceId),
      kodFolderPath: values.kodFolderPath!,
      files: selectedKodFiles.value,
    });
    attachmentFiles.value = mergeAttachmentFiles(attachmentFiles.value, attachments);
    await formApi.setFieldValue('attachmentFileIds', attachmentFiles.value as any);
    kodFileModalOpen.value = false;
    message.success('已添加可道云文件');
  } finally {
    kodFileLoading.value = false;
  }
}

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) {
      return;
    }
    if (!targets.value.length) {
      message.error('请至少配置一个分发对象');
      return;
    }
    if (targets.value.some((item) => item.targetType !== 1 && !item.targetId)) {
      message.error('请补充分发对象');
      return;
    }
    modalApi.lock();
    try {
      const data = (await formApi.getValues()) as SystemPartyFileApi.PartyFile;
      data.attachmentFileIds = resolveAttachmentFileIds(attachmentFiles.value);
      data.targets = targets.value as SystemPartyFileApi.PartyFileTarget[];
      await (formData.value?.id ? updatePartyFile(data) : createPartyFile(data));
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
      attachmentFiles.value = [];
      kodFolderTree.value = [];
      targets.value = [{ targetType: 1 }];
      storageTypeValue.value = 1;
      kodSourceIdValue.value = undefined;
      kodFolderPathValue.value = undefined;
      kodFileModalOpen.value = false;
      kodFileList.value = [];
      selectedKodFilePaths.value = [];
      selectedKodFiles.value = [];
      await formApi.resetForm();
      return;
    }
    const data = modalApi.getData<SystemPartyFileApi.PartyFile>();
    if (!data?.id) {
      formData.value = undefined;
      attachmentFiles.value = [];
      kodFolderTree.value = [];
      targets.value = [{ targetType: 1 }];
      storageTypeValue.value = 1;
      kodSourceIdValue.value = undefined;
      kodFolderPathValue.value = undefined;
      await formApi.setValues({
        storageType: 1,
        publishTime: dayjs().format('YYYY-MM-DD HH:mm:ss'),
        status: 0,
      });
      return;
    }
    modalApi.lock();
    try {
      formData.value = await getPartyFile(data.id);
      attachmentFiles.value = (formData.value.attachments || []) as any;
      storageTypeValue.value = Number(formData.value.storageType || 1);
      kodSourceIdValue.value = formData.value.kodSourceId;
      kodFolderPathValue.value = formData.value.kodFolderPath;
      targets.value = (formData.value.targets || []).map((item) => ({
        targetType: item.targetType,
        targetId: item.targetId,
      }));
      if (formData.value.kodSourceId) {
        kodFolderTree.value = await getPartyFileKodFolderTree(formData.value.kodSourceId);
      }
      await formApi.setValues({
        ...formData.value,
        attachmentFileIds: attachmentFiles.value as any,
      });
    } finally {
      modalApi.unlock();
    }
  },
});

async function handleKodSourceChange(value?: number) {
  kodFolderTree.value = value ? await getPartyFileKodFolderTree(value) : [];
  await formApi.updateSchema([
    {
      fieldName: 'kodFolderPath',
      componentProps: {
        treeData: kodFolderTree.value,
        fieldNames: { children: 'children', label: 'title', value: 'value' },
        treeNodeFilterProp: 'title',
        showSearch: true,
      },
    },
  ]);
  await formApi.setFieldValue('kodFolderPath', undefined);
  await formApi.setFieldValue('kodFolderName', '');
  kodFolderPathValue.value = undefined;
}

onMounted(async () => {
  const options = await buildTargetSelectOptions();
  users.value = options.users;
  depts.value = options.depts as SystemDeptApi.Dept[];
  roles.value = options.roles;
  const kodSources = await getSimplePartyFileKodSourceList();
  kodSourceOptions.value = kodSources.map((item) => ({ label: item.name, value: item.id! }));
  await formApi.updateSchema([
    {
      fieldName: 'kodSourceId',
      componentProps: {
        options: kodSourceOptions.value,
      },
    },
  ]);
});
</script>

<template>
  <Modal :title="getTitle" class="w-[960px]">
    <div class="mx-4">
      <FormRender />
      <Divider orientation="left">分发对象</Divider>
      <div class="space-y-3">
        <div
          v-for="(item, index) in targets"
          :key="index"
          class="flex items-center gap-3"
        >
          <Select
            :value="item.targetType"
            class="w-40"
            @update:value="handleTargetTypeChange(index, Number($event))"
          >
            <Select.Option :value="1">全员</Select.Option>
            <Select.Option :value="2">指定用户</Select.Option>
            <Select.Option :value="3">指定部门</Select.Option>
            <Select.Option :value="4">指定角色</Select.Option>
          </Select>
          <TreeSelect
            v-if="item.targetType === 3"
            v-model:value="item.targetId"
            class="flex-1"
            :tree-data="depts"
            :field-names="{ children: 'children', label: 'name', value: 'id' }"
            tree-default-expand-all
            placeholder="请选择部门"
          />
          <Select
            v-else-if="item.targetType !== 1"
            v-model:value="item.targetId"
            class="flex-1"
            :options="getTargetOptions(item.targetType)"
            placeholder="请选择对象"
            show-search
            option-filter-prop="label"
          />
          <Input
            v-else
            value="全员可见"
            class="flex-1"
            disabled
          />
          <Button
            v-if="item.targetType !== 1"
            danger
            @click="removeTarget(index)"
          >
            删除
          </Button>
        </div>
      </div>
      <div class="mt-3">
        <Button
          type="dashed"
          :disabled="targets.length === 1 && targets[0]?.targetType === 1"
          @click="appendTarget"
        >
          新增分发对象
        </Button>
      </div>
    </div>
  </Modal>
  <AModal
    v-model:open="kodFileModalOpen"
    title="选择可道云文件"
    width="900px"
    :confirm-loading="kodFileLoading"
    @ok="confirmKodFileSelection"
  >
    <Table
      :columns="kodFileColumns"
      :data-source="kodFileList"
      :loading="kodFileLoading"
      :pagination="false"
      row-key="path"
      :row-selection="{
        selectedRowKeys: selectedKodFilePaths,
        onChange: handleKodFileSelectionChange,
      }"
      size="small"
    />
  </AModal>
</template>
