#!/usr/bin/env node

const apiBaseUrl = (process.env.BPM_API_BASE || '').replace(/\/$/, '');
const accessToken = process.env.BPM_ADMIN_TOKEN;
const apply = process.argv.includes('--apply');

if (!apiBaseUrl || !accessToken) {
  throw new Error('BPM_API_BASE and BPM_ADMIN_TOKEN are required');
}

const USER_TASK_NODE = 11;
const END_NODE = 1;
const PRESIDENT_USER_ID = '215';

function isPresidentNode(node) {
  return (
    node?.type === USER_TASK_NODE &&
    String(node.candidateParam) === PRESIDENT_USER_ID
  );
}

function findTerminalPresident(branch) {
  let beforePresident;
  let current = branch.childNode;
  while (current?.id) {
    if (isPresidentNode(current)) {
      const next = current.childNode;
      if (!next?.id || next.type === END_NODE) {
        return { beforePresident, president: current };
      }
    }
    beforePresident = current;
    current = current.childNode;
  }
  return undefined;
}

function findBranchGateways(node, gateways = []) {
  if (!node?.id) {
    return gateways;
  }
  if (Array.isArray(node.conditionNodes) && node.conditionNodes.length > 0) {
    gateways.push(node);
    for (const branch of node.conditionNodes) {
      findBranchGateways(branch.childNode, gateways);
    }
  }
  findBranchGateways(node.childNode, gateways);
  return gateways;
}

function normalizeGateway(gateway) {
  if (isPresidentNode(gateway.childNode)) {
    return { changed: false, reason: 'already-shared' };
  }
  const terminals = gateway.conditionNodes.map(findTerminalPresident);
  if (terminals.some((terminal) => !terminal)) {
    return { changed: false, reason: 'not-every-branch-ends-with-president' };
  }
  if (!gateway.childNode || gateway.childNode.type !== END_NODE) {
    return { changed: false, reason: 'missing-canonical-end-node' };
  }

  const sharedPresident = structuredClone(terminals[0].president);
  const endNode = gateway.childNode;
  sharedPresident.childNode = endNode;

  terminals.forEach((terminal, index) => {
    const branch = gateway.conditionNodes[index];
    if (terminal.beforePresident) {
      delete terminal.beforePresident.childNode;
    } else {
      delete branch.childNode;
    }
  });
  gateway.childNode = sharedPresident;
  return { changed: true, branchCount: terminals.length };
}

function normalizeSimpleModel(simpleModel) {
  const gateways = findBranchGateways(simpleModel);
  const results = gateways.map(normalizeGateway);
  const changed = results.filter((result) => result.changed);
  const unsupported = results.filter(
    (result) => !result.changed && result.reason !== 'already-shared',
  );
  if (unsupported.length > 0) {
    throw new Error(
      `unsupported gateway structure: ${unsupported
        .map((result) => result.reason)
        .join(', ')}`,
    );
  }
  return { changedGateways: changed.length, changedBranches: changed.reduce((sum, result) => sum + result.branchCount, 0) };
}

async function request(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}/admin-api${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  const payload = await response.json();
  if (!response.ok || payload.code !== 0) {
    throw new Error(`${options.method || 'GET'} ${path}: ${payload.msg || response.status}`);
  }
  return payload.data;
}

function toUpdatePayload(model, simpleModel) {
  const keys = [
    'id',
    'key',
    'name',
    'category',
    'icon',
    'description',
    'type',
    'formType',
    'formId',
    'formCustomCreatePath',
    'formCustomViewPath',
    'visible',
    'startUserIds',
    'startDeptIds',
    'managerUserIds',
    'sort',
    'allowCancelRunningProcess',
    'allowWithdrawTask',
    'processIdRule',
    'autoApprovalType',
    'titleSetting',
    'summarySetting',
    'processBeforeTriggerSetting',
    'processAfterTriggerSetting',
    'taskBeforeTriggerSetting',
    'taskAfterTriggerSetting',
    'printTemplateSetting',
  ];
  const payload = Object.fromEntries(
    keys.map((key) => [key, model[key]]).filter(([, value]) => value !== undefined),
  );
  return { ...payload, simpleModel };
}

const models = await request('/bpm/model/list');
const simpleModels = models.filter((model) => model.type === 20);

for (const model of simpleModels) {
  const original = await request(`/bpm/model/get?id=${encodeURIComponent(model.id)}`);
  const simpleModel = structuredClone(original.simpleModel);
  const result = normalizeSimpleModel(simpleModel);
  console.log(`${model.key}: ${result.changedGateways} gateway(s), ${result.changedBranches} branch(es)`);

  if (!apply || result.changedGateways === 0) {
    continue;
  }
  await request('/bpm/model/update', {
    method: 'PUT',
    body: JSON.stringify(toUpdatePayload(original, simpleModel)),
  });
  await request(`/bpm/model/deploy?id=${encodeURIComponent(model.id)}`, {
    method: 'POST',
  });
}

console.log(apply ? 'Migration applied.' : 'Dry run complete. Use --apply to publish changes.');
