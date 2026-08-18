import { requestClient } from '#/api/request';

export interface AgentModelProvider {
  id?: number;
  name: string;
  provider_type: string;
  base_url: string;
  source: string;
  enabled: boolean;
  credential_status?: string;
}

export interface AgentModel {
  id: number;
  provider_id: number;
  provider_name: string;
  model_name: string;
  display_name?: string;
  capabilities?: Record<string, unknown>;
  enabled: boolean;
}

export interface AgentModelBinding {
  id: number;
  user_id?: number | null;
  agent_name: string;
  model_id: number;
  model_name: string;
  display_name?: string;
  provider_name: string;
  enabled: boolean;
}

export function getModelProviders() {
  return requestClient.get<AgentModelProvider[]>('/agent/model-providers');
}

export function saveModelProvider(data: Record<string, unknown>) {
  return requestClient.post<AgentModelProvider>('/agent/model-providers', data);
}

export function deleteModelProvider(id: number) {
  return requestClient.delete(`/agent/model-providers/${id}`);
}

export function testModelProvider(id: number) {
  return requestClient.post<{ success: boolean; count: number; error?: string }>(
    `/agent/model-providers/${id}/test`,
  );
}

export function syncModelProvider(id: number) {
  return requestClient.post<{ success: boolean; count: number }>(
    `/agent/model-providers/${id}/sync-models`,
  );
}

export function getAgentModels(providerId?: number) {
  return requestClient.get<AgentModel[]>('/agent/models', {
    params: providerId ? { providerId } : undefined,
  });
}

export function updateModelCapabilities(
  id: number,
  capabilities: Record<string, unknown>,
) {
  return requestClient.put(`/agent/models/${id}/capabilities`, capabilities);
}

export function getModelBindings() {
  return requestClient.get<AgentModelBinding[]>('/agent/model-bindings');
}

export function saveModelBinding(data: Record<string, unknown>) {
  return requestClient.post<AgentModelBinding>('/agent/model-bindings', data);
}

export function deleteModelBinding(id: number) {
  return requestClient.delete(`/agent/model-bindings/${id}`);
}
