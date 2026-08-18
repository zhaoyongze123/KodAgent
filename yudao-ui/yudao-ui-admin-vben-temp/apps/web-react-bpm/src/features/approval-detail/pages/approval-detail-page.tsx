import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowsClockwise } from '@phosphor-icons/react';
import { useParams, useSearchParams } from 'react-router-dom';

import { getOARecord, type OAModuleKey } from '@/entities/oa/api/oa-api';
import {
  cancelByStartUser,
  getApprovalDetail,
} from '@/entities/process-instance/api/process-instance-api';
import { ApprovalActionPanel } from '@/features/approval-detail/components/approval-action-panel';
import { oaModuleConfigs } from '@/features/oa/config/oa-module-config';
import { formatDateTime } from '@/shared/lib/format';
import { StatusPill } from '@/shared/ui/status-pill';

function resolveOAModuleKey(processDefinitionKey?: string) {
  if (!processDefinitionKey?.startsWith('oa_')) {
    return null;
  }
  const key = processDefinitionKey.slice(3) as OAModuleKey;
  return key in oaModuleConfigs ? key : null;
}

function renderVariableValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.join('、');
  }
  if (typeof value === 'string' && value.startsWith('[') && value.endsWith(']')) {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.join('、');
      }
    } catch {}
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  return String(value ?? '-');
}

function parseFileList(value: unknown) {
  if (Array.isArray(value)) {
    return value.map(String).filter(Boolean);
  }
  if (typeof value === 'string') {
    if (value.startsWith('[') && value.endsWith(']')) {
      try {
        const parsed = JSON.parse(value) as unknown;
        if (Array.isArray(parsed)) {
          return parsed.map(String).filter(Boolean);
        }
      } catch {}
    }
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

export function ApprovalDetailPage() {
  const { processInstanceId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get('taskId') || undefined;

  const detailQuery = useQuery({
    queryKey: ['approval-detail', processInstanceId, taskId],
    queryFn: () =>
      getApprovalDetail({
        processInstanceId,
        taskId,
      }),
  });

  const oaModuleKey = resolveOAModuleKey(detailQuery.data?.processDefinition.key);
  const oaRecordQuery = useQuery({
    enabled: Boolean(oaModuleKey && detailQuery.data?.processInstance.businessKey),
    queryKey: ['oa-record', oaModuleKey, detailQuery.data?.processInstance.businessKey],
    queryFn: () =>
      getOARecord(
        oaModuleKey!,
        Number(detailQuery.data?.processInstance.businessKey || 0),
      ),
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      cancelByStartUser(detailQuery.data?.processInstance.id || 0, '发起人撤销'),
  });

  const detail = detailQuery.data;
  const summary = detail?.processInstance.summary || [];
  const variables = Object.entries(detail?.processInstance.formVariables || {});
  const oaConfig = oaModuleKey ? oaModuleConfigs[oaModuleKey] : null;
  const oaRecord = oaRecordQuery.data;
  const activeNode = detail?.activityNodes.find((node) => node.status === 1);
  const finishedNodeCount = (detail?.activityNodes || []).filter(
    (node) => node.status !== 0 && node.status !== 1,
  ).length;

  function renderOADetailValue(
    field: NonNullable<typeof oaConfig>['detailFields'][number],
    value: unknown,
  ) {
    if (field.type === 'files') {
      const files = parseFileList(value);
      if (files.length === 0) {
        return <span>-</span>;
      }
      return (
        <div className="space-y-1">
          {files.map((file) => (
            <a
              key={file}
              className="block text-[var(--accent)] underline-offset-2 hover:underline"
              href={file}
              rel="noreferrer"
              target="_blank"
            >
              {file}
            </a>
          ))}
        </div>
      );
    }
    if (field.type === 'datetime') {
      return <span>{formatDateTime(value as string)}</span>;
    }
    if (field.type === 'switch') {
      return <span>{value ? '是' : '否'}</span>;
    }
    if (field.field === 'type' && oaConfig) {
      const matched = oaConfig.fields
        .find((item) => item.field === 'type')
        ?.options?.find((item) => String(item.value) === String(value));
      return <span>{matched?.label || renderVariableValue(value)}</span>;
    }
    return <span>{renderVariableValue(value)}</span>;
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.95fr)_340px]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">审批详情</div>
            <h2>{detail?.processInstance.name || '流程详情'}</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="subtle-chip"
              type="button"
              onClick={() => {
                detailQuery.refetch();
                oaRecordQuery.refetch();
              }}
            >
              <ArrowsClockwise size={14} />
              刷新详情
            </button>
            <StatusPill status={detail?.processInstance.status} />
          </div>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">发起人</div>
            <div className="mt-2 font-medium">
              {detail?.processInstance.startUser?.nickname || '-'}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">所属分类</div>
            <div className="mt-2 font-medium">
              {detail?.processInstance.categoryName || '-'}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">创建时间</div>
            <div className="mt-2 font-medium tabular-nums">
              {formatDateTime(detail?.processInstance.createTime)}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">流程编号</div>
            <div className="mt-2 font-medium tabular-nums">
              {detail?.processInstance.id || '-'}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">当前节点</div>
            <div className="mt-2 font-medium">{activeNode?.name || '已结束'}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">已完成节点</div>
            <div className="mt-2 font-medium tabular-nums">{finishedNodeCount}</div>
          </div>
        </div>

        <div className="detail-block">
          <div className="mb-3 text-sm font-medium">申请摘要</div>
          <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
            {summary.map((item) => (
              <div key={item.key} className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 text-sm">
                <div className="text-[var(--text-muted)]">{item.key}</div>
                <div>{item.value}</div>
              </div>
            ))}
          </div>
        </div>

        {oaConfig && oaRecord ? (
          <div className="detail-block">
            <div className="mb-3 text-sm font-medium">业务单据</div>
            <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
              {oaConfig.detailFields.map((field) => (
                <div
                  key={field.field}
                  className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 text-sm"
                >
                  <div className="text-[var(--text-muted)]">{field.label}</div>
                  <div className="break-all">
                    {renderOADetailValue(field, oaRecord[field.field])}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="detail-block">
          <div className="mb-3 text-sm font-medium">流程变量</div>
          <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
            {variables.map(([key, value]) => (
              <div key={key} className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 text-sm">
                <div className="text-[var(--text-muted)]">{key}</div>
                <div className="break-all">{renderVariableValue(value)}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">流程跟踪</div>
            <h3>节点流转</h3>
          </div>
        </div>

        <div className="work-list border-b border-[var(--line)]">
          {(detail?.activityNodes || []).map((node) => (
            <div
              key={node.id}
              className="border-b border-[var(--line)] px-5 py-4 last:border-b-0"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-medium">{node.name}</div>
                  <div className="mt-1 text-sm text-[var(--text-muted)]">
                    {formatDateTime(node.startTime)} - {formatDateTime(node.endTime)}
                  </div>
                </div>
                <StatusPill status={node.status} />
              </div>

              <div className="mt-3 space-y-2">
                {node.tasks.map((task) => (
                  <div
                    key={task.id}
                    className="grid grid-cols-[128px_minmax(0,1fr)] gap-3 border-t border-[var(--line)] pt-2 text-sm"
                  >
                    <div className="text-[var(--text-muted)]">
                      {task.assigneeUser?.nickname || '待分配'}
                    </div>
                    <div>{task.reason || '暂无审批意见'}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <aside className="space-y-4">
        <section className="surface overflow-hidden">
          <div className="section-heading">
            <div>
              <div className="hairline-title">当前动作</div>
              <h3>处理入口</h3>
            </div>
          </div>
          <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-2">
            <div className="detail-block">
              <div className="work-meta">待处理任务</div>
              <div className="mt-2 text-sm font-medium">
                {detail?.todoTask?.name || '当前无待办'}
              </div>
            </div>
            <div className="detail-block">
              <div className="work-meta">可退回节点</div>
              <div className="mt-2 text-sm font-medium tabular-nums">
                {detail?.activityNodes.length || 0}
              </div>
            </div>
          </div>
          <div className="px-4 py-4">
            <button
              className="w-full border border-[var(--line)] bg-white px-4 py-3 text-sm font-medium"
              disabled={cancelMutation.isPending}
              type="button"
              onClick={() => cancelMutation.mutate()}
            >
              发起人撤销
            </button>
          </div>
        </section>
        <ApprovalActionPanel processInstanceId={processInstanceId} task={detail?.todoTask} />
      </aside>
    </div>
  );
}
