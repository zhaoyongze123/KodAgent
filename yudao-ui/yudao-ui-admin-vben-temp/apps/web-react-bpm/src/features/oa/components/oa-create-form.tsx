import { useMutation, useQueries, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { getSimpleDeptList } from '@/entities/dept/api/dept-api';
import {
  createOARecord,
  type OAModuleKey,
} from '@/entities/oa/api/oa-api';
import { getProcessDefinition } from '@/entities/process-definition/api/process-definition-api';
import {
  getApprovalDetail,
  type ApprovalNodeInfo,
} from '@/entities/process-instance/api/process-instance-api';
import { getSimpleUserList, getUserProfile } from '@/entities/user/api/user-api';
import {
  oaModuleConfigs,
  type OAFieldConfig,
} from '@/features/oa/config/oa-module-config';

function normalizeDatetimeValue(value: string) {
  if (!value) {
    return value;
  }
  return `${value}:00`;
}

function buildProcessVariables(
  formState: Record<string, unknown>,
  fields: OAFieldConfig[],
) {
  const payload: Record<string, unknown> = {};
  fields.forEach((field) => {
    const value = formState[field.field];
    if (value === undefined || value === '') {
      return;
    }
    if (field.type === 'datetime' && typeof value === 'string') {
      payload[field.field] = normalizeDatetimeValue(value);
      return;
    }
    if (field.type === 'number' && typeof value === 'string') {
      payload[field.field] = Number(value);
      return;
    }
    if (field.type === 'switch') {
      payload[field.field] = Boolean(value);
      return;
    }
    if (
      (field.type === 'user-multi-select' ||
        field.type === 'dept-multi-select' ||
        field.type === 'files') &&
      Array.isArray(value)
    ) {
      payload[field.field] = value;
      return;
    }
    if (field.type === 'user-select' && typeof value === 'number') {
      payload[field.field] = value;
      return;
    }
    if (field.field === 'type' && typeof value === 'string' && /^[0-9]+$/.test(value)) {
      payload[field.field] = Number(value);
      return;
    }
    payload[field.field] = value;
  });
  return payload;
}

function flattenApprovalNodes(nodes: ApprovalNodeInfo[]) {
  return nodes.filter((node) => Array.isArray(node.candidateUsers) && node.candidateUsers.length > 0);
}

interface OACreateFormProps {
  moduleKey: OAModuleKey;
}

export function OACreateForm({ moduleKey }: OACreateFormProps) {
  const navigate = useNavigate();
  const config = oaModuleConfigs[moduleKey];
  const [formState, setFormState] = useState<Record<string, unknown>>({});
  const [submitError, setSubmitError] = useState('');
  const [startUserSelectAssignees, setStartUserSelectAssignees] = useState<
    Record<string, number[]>
  >({});

  const [profileQuery, userQuery, deptQuery] = useQueries({
    queries: [
      { queryKey: ['profile'], queryFn: getUserProfile },
      { queryKey: ['simple-users'], queryFn: getSimpleUserList },
      { queryKey: ['simple-depts'], queryFn: getSimpleDeptList },
    ],
  });

  const definitionQuery = useQuery({
    queryKey: ['process-definition', config.processDefinitionKey],
    queryFn: () => getProcessDefinition(undefined, config.processDefinitionKey),
  });

  const previewQuery = useQuery({
    enabled: Boolean(definitionQuery.data?.id),
    queryKey: ['oa-preview', moduleKey, definitionQuery.data?.id, formState],
    queryFn: () =>
      getApprovalDetail({
        activityId: 'StartUserNode',
        processDefinitionId: definitionQuery.data?.id,
        processVariablesStr: JSON.stringify(buildProcessVariables(formState, config.fields)),
      }),
  });

  const selectableNodes = useMemo(
    () => flattenApprovalNodes(previewQuery.data?.activityNodes || []),
    [previewQuery.data?.activityNodes],
  );

  useEffect(() => {
    if (!profileQuery.data) {
      return;
    }
    setFormState((previous) => ({
      ...previous,
      applicantName: profileQuery.data.nickname,
      deptName: profileQuery.data.dept?.name || '',
    }));
  }, [profileQuery.data]);

  useEffect(() => {
    if (selectableNodes.length === 0) {
      setStartUserSelectAssignees({});
      return;
    }
    setStartUserSelectAssignees((previous) => {
      const nextState: Record<string, number[]> = {};
      selectableNodes.forEach((node) => {
        nextState[node.id] = previous[node.id] || [];
      });
      return nextState;
    });
  }, [selectableNodes]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!definitionQuery.data?.id) {
        throw new Error(`流程 ${config.title} 未配置，无法发起`);
      }

      for (const field of config.fields) {
        if (!field.required) {
          continue;
        }
        const value = formState[field.field];
        if (field.type === 'switch') {
          continue;
        }
        if (
          (field.type === 'user-multi-select' ||
            field.type === 'dept-multi-select' ||
            field.type === 'files') &&
          Array.isArray(value)
        ) {
          if (value.length === 0) {
            throw new Error(`${field.label}不能为空`);
          }
          continue;
        }
        if (value === undefined || value === null || value === '') {
          throw new Error(`${field.label}不能为空`);
        }
      }

      for (const node of selectableNodes) {
        if ((startUserSelectAssignees[node.id] || []).length === 0) {
          throw new Error(`请选择 ${node.name} 的审批人`);
        }
      }

      const payload = buildProcessVariables(formState, config.fields);
      if (Object.keys(startUserSelectAssignees).length > 0) {
        payload.startUserSelectAssignees = startUserSelectAssignees;
      }
      return createOARecord(moduleKey, payload);
    },
    onError: (error) => {
      setSubmitError(error instanceof Error ? error.message : '提交失败');
    },
    onSuccess: () => {
      setSubmitError('');
      navigate('/center/initiated');
    },
  });

  const userOptions = userQuery.data || [];
  const deptOptions = deptQuery.data || [];

  function updateField(field: string, value: unknown) {
    setFormState((previous) => ({
      ...previous,
      [field]: value,
    }));
  }

  function renderMultiSelect(
    field: OAFieldConfig,
    options: Array<{ id: number; name?: string; nickname?: string }>,
    value: unknown,
  ) {
    const selected = Array.isArray(value) ? value.map(String) : [];
    return (
      <select
        className="w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
        multiple
        size={Math.min(Math.max(options.length, 4), 8)}
        value={selected}
        onChange={(event) => {
          const nextValue = Array.from(event.target.selectedOptions).map((option) =>
            Number(option.value),
          );
          updateField(field.field, nextValue);
        }}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.nickname || option.name}
          </option>
        ))}
      </select>
    );
  }

  function renderField(field: OAFieldConfig) {
    const value = formState[field.field];
    const className =
      'w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none';

    if (field.type === 'textarea') {
      return (
        <textarea
          className={className}
          placeholder={field.placeholder}
          rows={field.rows || 4}
          value={String(value || '')}
          onChange={(event) => updateField(field.field, event.target.value)}
        />
      );
    }
    if (field.type === 'datetime') {
      return (
        <input
          className={className}
          type="datetime-local"
          value={String(value || '')}
          onChange={(event) => updateField(field.field, event.target.value)}
        />
      );
    }
    if (field.type === 'switch') {
      return (
        <label className="flex items-center gap-3 text-sm">
          <input
            checked={Boolean(value)}
            type="checkbox"
            onChange={(event) => updateField(field.field, event.target.checked)}
          />
          <span>{Boolean(value) ? '是' : '否'}</span>
        </label>
      );
    }
    if (field.options) {
      return (
        <select
          className={className}
          value={String(value || '')}
          onChange={(event) => updateField(field.field, event.target.value)}
        >
          <option value="">请选择</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }
    if (field.type === 'user-select') {
      return (
        <select
          className={className}
          value={value ? String(value) : ''}
          onChange={(event) =>
            updateField(field.field, event.target.value ? Number(event.target.value) : '')
          }
        >
          <option value="">请选择用户</option>
          {userOptions.map((item) => (
            <option key={item.id} value={item.id}>
              {item.nickname}#{item.id}
            </option>
          ))}
        </select>
      );
    }
    if (field.type === 'user-multi-select') {
      return renderMultiSelect(field, userOptions, value);
    }
    if (field.type === 'dept-multi-select') {
      return renderMultiSelect(field, deptOptions, value);
    }
    if (field.type === 'files') {
      const fileValue = Array.isArray(value) ? value.join('\n') : '';
      return (
        <textarea
          className={className}
          placeholder="请输入文件 URL，每行一个"
          rows={3}
          value={fileValue}
          onChange={(event) =>
            updateField(
              field.field,
              event.target.value
                .split('\n')
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
        />
      );
    }
    return (
      <input
        className={className}
        placeholder={field.placeholder}
        type={field.type === 'number' ? 'number' : 'text'}
        value={String(value || '')}
        onChange={(event: ChangeEvent<HTMLInputElement>) =>
          updateField(field.field, event.target.value)
        }
      />
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
      <form className="surface px-6 py-5" onSubmit={handleSubmit}>
        <div className="border-b border-[var(--line)] pb-4">
          <div className="hairline-title">{config.categoryLabel}</div>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">{config.title}</h2>
          <div className="mt-2 text-sm text-[var(--text-muted)]">{config.description}</div>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {config.fields.map((field) => (
            <div
              key={field.field}
              className={
                field.type === 'textarea' ||
                field.type === 'files' ||
                field.type === 'user-multi-select' ||
                field.type === 'dept-multi-select'
                  ? 'md:col-span-2'
                  : ''
              }
            >
              <label className="mb-2 block text-sm font-medium">
                {field.label}
                {field.required ? <span className="ml-1 text-[var(--danger)]">*</span> : null}
              </label>
              {renderField(field)}
            </div>
          ))}
        </div>
        {submitError ? (
          <div className="mt-4 border border-[#dfb2aa] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
            {submitError}
          </div>
        ) : null}
        <div className="mt-6 flex items-center justify-end gap-3 border-t border-[var(--line)] pt-4">
          <button
            className="border border-[var(--line)] bg-white px-4 py-2 text-sm"
            type="button"
            onClick={() => navigate('/launch')}
          >
            取消
          </button>
          <button
            className="border border-[#0f56a6] bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
            disabled={mutation.isPending}
            type="submit"
          >
            {mutation.isPending ? '提交中...' : '提交审批'}
          </button>
        </div>
      </form>

      <aside className="space-y-4">
        <section className="surface px-4 py-4">
          <div className="hairline-title">申请摘要</div>
          <div className="mt-3 space-y-3 text-sm">
            {config.summaryFields.map((fieldKey) => (
              <div key={fieldKey} className="grid grid-cols-[108px_minmax(0,1fr)] gap-3">
                <div className="text-[var(--text-muted)]">
                  {config.fields.find((field) => field.field === fieldKey)?.label || fieldKey}
                </div>
                <div className="break-all">
                  {Array.isArray(formState[fieldKey])
                    ? (formState[fieldKey] as Array<string | number>).join('、') || '-'
                    : String(formState[fieldKey] || '-')}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="surface px-4 py-4">
          <div className="hairline-title">流程定义</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            后端流程 Key：{config.processDefinitionKey}
          </div>
          <div className="mt-1 text-sm text-[var(--text-muted)]">
            流程定义 ID：{definitionQuery.data?.id || '未配置'}
          </div>
        </section>

        <section className="surface px-4 py-4">
          <div className="hairline-title">审批预览</div>
          <div className="mt-3 space-y-3 text-sm">
            {selectableNodes.length === 0 ? (
              <div className="text-[var(--text-muted)]">
                {previewQuery.isLoading ? '正在加载审批路径...' : '当前流程无发起人自选审批节点'}
              </div>
            ) : (
              selectableNodes.map((node) => (
                <div key={node.id} className="border-b border-[var(--line)] pb-3 last:border-b-0 last:pb-0">
                  <div className="font-medium">{node.name}</div>
                  <div className="mt-2 text-xs text-[var(--text-muted)]">请选择该节点审批人</div>
                  <select
                    className="mt-2 w-full border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none"
                    multiple
                    size={Math.min(Math.max(node.candidateUsers?.length || 0, 3), 6)}
                    value={(startUserSelectAssignees[node.id] || []).map(String)}
                    onChange={(event) => {
                      const nextValue = Array.from(event.target.selectedOptions).map((option) =>
                        Number(option.value),
                      );
                      setStartUserSelectAssignees((previous) => ({
                        ...previous,
                        [node.id]: nextValue,
                      }));
                    }}
                  >
                    {(node.candidateUsers || []).map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.nickname}#{user.id}
                      </option>
                    ))}
                  </select>
                </div>
              ))
            )}
          </div>
        </section>
      </aside>
    </div>
  );
}
