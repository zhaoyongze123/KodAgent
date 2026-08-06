<script lang="ts" setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { message, Modal } from 'ant-design-vue';

import {
  deleteModelBinding,
  deleteModelProvider,
  getAgentModels,
  getModelBindings,
  getModelProviders,
  saveModelBinding,
  saveModelProvider,
  syncModelProvider,
  testModelProvider,
  type AgentModel,
  type AgentModelBinding,
  type AgentModelProvider,
} from '#/api/agent/model';

const loading = ref(false);
const providers = ref<AgentModelProvider[]>([]);
const models = ref<AgentModel[]>([]);
const bindings = ref<AgentModelBinding[]>([]);
const providerModal = ref(false);
const bindingModal = ref(false);
const editingProvider = ref<AgentModelProvider | null>(null);
const providerForm = reactive({ name: '', providerType: 'OPENAI_COMPATIBLE', baseUrl: '', apiKey: '', enabled: true });
const bindingForm = reactive<{ agentName: string; userId?: number; modelId?: number }>({ agentName: 'oa-main-agent' });

const modelOptions = computed(() => models.value.map((item) => ({
  label: `${item.provider_name} / ${item.display_name || item.model_name}`,
  value: item.id,
})));

async function reload() {
  loading.value = true;
  try {
    [providers.value, models.value, bindings.value] = await Promise.all([
      getModelProviders(),
      getAgentModels(),
      getModelBindings(),
    ]);
  } finally {
    loading.value = false;
  }
}

function openProvider(row?: AgentModelProvider) {
  editingProvider.value = row || null;
  Object.assign(providerForm, {
    name: row?.name || '', providerType: row?.provider_type || 'OPENAI_COMPATIBLE',
    baseUrl: row?.base_url || '', apiKey: '', enabled: row?.enabled ?? true,
  });
  providerModal.value = true;
}

async function submitProvider() {
  if (!providerForm.name || !providerForm.baseUrl || (!editingProvider.value && !providerForm.apiKey)) {
    message.warning('名称、Base URL 和新供应商 API Key 必填');
    return;
  }
  await saveModelProvider({ ...providerForm, ...(editingProvider.value ? { id: editingProvider.value.id } : {}) });
  providerModal.value = false;
  message.success('供应商已保存');
  await reload();
}

async function testProvider(row: AgentModelProvider) {
  const result = await testModelProvider(row.id!);
  result.success ? message.success(`连接成功，发现 ${result.count} 个模型`) : message.error(result.error || '连接失败');
  await reload();
}

async function syncProvider(row: AgentModelProvider) {
  const result = await syncModelProvider(row.id!);
  message.success(`已同步 ${result.count} 个模型`);
  await reload();
}

function confirmDeleteProvider(row: AgentModelProvider) {
  Modal.confirm({ title: `停用供应商“${row.name}”？`, onOk: async () => { await deleteModelProvider(row.id!); await reload(); } });
}

function openBinding() {
  Object.assign(bindingForm, { agentName: 'oa-main-agent', userId: undefined, modelId: undefined });
  bindingModal.value = true;
}

async function submitBinding() {
  if (!bindingForm.modelId) { message.warning('请选择默认模型'); return; }
  await saveModelBinding({ ...bindingForm, userId: bindingForm.userId || null });
  bindingModal.value = false;
  message.success('默认模型已保存');
  await reload();
}

function removeBinding(row: AgentModelBinding) {
  Modal.confirm({ title: '删除这条模型绑定？', onOk: async () => { await deleteModelBinding(row.id); await reload(); } });
}

onMounted(reload);
</script>

<template>
  <Page auto-content-height>
    <a-card title="模型供应商" :loading="loading" class="mb-4">
      <template #extra><a-button type="primary" @click="openProvider()">新增供应商</a-button></template>
      <a-table :data-source="providers" :pagination="false" row-key="id" size="small">
        <a-table-column key="name" title="名称" data-index="name" />
        <a-table-column key="baseUrl" title="Base URL" data-index="baseUrl" />
        <a-table-column key="credentialStatus" title="密钥状态">
          <template #default="{ record }"><a-tag :color="record.credential_status === 'VALID' ? 'green' : 'orange'">{{ record.credential_status || 'UNKNOWN' }}</a-tag></template>
        </a-table-column>
        <a-table-column key="enabled" title="状态"><template #default="{ record }"><a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag></template></a-table-column>
        <a-table-column key="actions" title="操作" :width="260">
          <template #default="{ record }">
            <a-space><a-button type="link" size="small" @click="openProvider(record)">编辑</a-button><a-button type="link" size="small" @click="testProvider(record)">测试</a-button><a-button type="link" size="small" @click="syncProvider(record)">同步模型</a-button><a-button danger type="link" size="small" @click="confirmDeleteProvider(record)">停用</a-button></a-space>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <a-card title="已同步模型" :loading="loading" class="mb-4">
      <a-table :data-source="models" :pagination="{ pageSize: 10 }" row-key="id" size="small">
        <a-table-column title="供应商" data-index="provider_name" /><a-table-column title="模型" data-index="model_name" /><a-table-column title="展示名称" data-index="display_name" />
        <a-table-column title="能力"><template #default="{ record }"><a-space><a-tag v-if="record.capabilities?.streaming">流式</a-tag><a-tag v-if="record.capabilities?.tools">工具</a-tag><a-tag v-if="record.capabilities?.vision">视觉</a-tag></a-space></template></a-table-column>
      </a-table>
    </a-card>

    <a-card title="默认模型绑定" :loading="loading">
      <template #extra><a-button type="primary" @click="openBinding">新增绑定</a-button></template>
      <a-table :data-source="bindings" :pagination="false" row-key="id" size="small">
        <a-table-column title="作用域"><template #default="{ record }">{{ record.user_id ? `用户 ${record.user_id}` : '租户默认' }}</template></a-table-column><a-table-column title="Agent" data-index="agent_name" /><a-table-column title="模型"><template #default="{ record }">{{ record.provider_name }} / {{ record.display_name || record.model_name }}</template></a-table-column><a-table-column title="操作"><template #default="{ record }"><a-button danger type="link" size="small" @click="removeBinding(record)">删除</a-button></template></a-table-column>
      </a-table>
    </a-card>

    <a-modal v-model:open="providerModal" :title="editingProvider ? '编辑供应商' : '新增供应商'" @ok="submitProvider">
      <a-form layout="vertical"><a-form-item label="名称" required><a-input v-model:value="providerForm.name" placeholder="例如：硅基流动" /></a-form-item><a-form-item label="Base URL" required><a-input v-model:value="providerForm.baseUrl" placeholder="https://api.siliconflow.cn/v1" /></a-form-item><a-form-item label="API Key" :required="!editingProvider"><a-input-password v-model:value="providerForm.apiKey" placeholder="仅提交时写入，页面不会回显" /></a-form-item></a-form>
    </a-modal>
    <a-modal v-model:open="bindingModal" title="新增默认模型绑定" @ok="submitBinding">
      <a-form layout="vertical"><a-form-item label="Agent 名称"><a-input v-model:value="bindingForm.agentName" /></a-form-item><a-form-item label="用户 ID（留空表示租户默认）"><a-input-number v-model:value="bindingForm.userId" :min="1" style="width: 100%" /></a-form-item><a-form-item label="模型" required><a-select v-model:value="bindingForm.modelId" :options="modelOptions" placeholder="选择模型" /></a-form-item></a-form>
    </a-modal>
  </Page>
</template>
