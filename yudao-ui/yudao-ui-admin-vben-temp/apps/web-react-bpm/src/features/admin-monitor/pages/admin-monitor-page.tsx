import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowsClockwise, MagnifyingGlass } from '@phosphor-icons/react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  cancelByAdmin,
  getManagerProcessInstances,
} from '@/entities/process-instance/api/process-instance-api';
import { getManagerTasks } from '@/entities/task/api/task-api';
import { formatDateTime } from '@/shared/lib/format';
import { StatusPill } from '@/shared/ui/status-pill';

const monitorTabs = [
  { key: 'instances', label: '流程实例', subtitle: '按流程实例跟踪全局运行情况' },
  { key: 'tasks', label: '流程任务', subtitle: '按任务视角处理积压、转办和超时' },
  { key: 'reports', label: '流程报表', subtitle: '汇总最近实例，用于监管盘点' },
] as const;

export function AdminMonitorPage() {
  const { monitorType = 'instances' } = useParams();
  const [keyword, setKeyword] = useState('');
  const [cancelReason, setCancelReason] = useState('管理员人工撤回');
  const [actionError, setActionError] = useState('');

  const instanceQuery = useQuery({
    enabled: monitorType === 'instances' || monitorType === 'reports',
    queryKey: ['admin-monitor', monitorType, 'instances'],
    queryFn: () => getManagerProcessInstances({ pageNo: 1, pageSize: 20 }),
  });
  const taskQuery = useQuery({
    enabled: monitorType === 'tasks',
    queryKey: ['admin-monitor', 'tasks'],
    queryFn: () => getManagerTasks({ pageNo: 1, pageSize: 20 }),
  });

  const currentTab =
    monitorTabs.find((item) => item.key === monitorType) || monitorTabs[0];
  const instanceRows = instanceQuery.data?.list || [];
  const taskRows = taskQuery.data?.list || [];
  const filteredInstanceRows = useMemo(() => {
    if (!keyword.trim()) {
      return instanceRows;
    }
    const nextKeyword = keyword.trim().toLowerCase();
    return instanceRows.filter((item) =>
      JSON.stringify(item).toLowerCase().includes(nextKeyword),
    );
  }, [instanceRows, keyword]);
  const filteredTaskRows = useMemo(() => {
    if (!keyword.trim()) {
      return taskRows;
    }
    const nextKeyword = keyword.trim().toLowerCase();
    return taskRows.filter((item) =>
      JSON.stringify(item).toLowerCase().includes(nextKeyword),
    );
  }, [keyword, taskRows]);
  const pendingTaskCount = taskRows.filter((item) => !item.endTime).length;
  const runningInstanceCount = instanceRows.filter((item) => !item.endTime).length;
  const cancelMutation = useMutation({
    mutationFn: async (id: number) => cancelByAdmin(id, cancelReason),
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '管理员撤回失败');
    },
    onSuccess: async () => {
      setActionError('');
      await instanceQuery.refetch();
    },
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">流程监管</div>
          <h2>{currentTab.label}</h2>
        </div>
        <div className="shell-subtitle max-w-[420px] text-right text-pretty">
          {currentTab.subtitle}
        </div>
      </div>

      <div className="border-b border-[var(--line)] px-5 py-4">
        <div className="flex flex-wrap gap-2">
          {monitorTabs.map((item) => (
            <Link
              key={item.key}
              className={
                item.key === monitorType
                  ? 'subtle-chip border-[var(--line-strong)] bg-white text-[var(--text)]'
                  : 'subtle-chip bg-[var(--panel-muted)] text-[var(--text-muted)]'
              }
              to={`/admin/${item.key}`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">当前视图</div>
          <div className="mt-2 text-lg font-semibold">{currentTab.label}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">实例运行中</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {runningInstanceCount}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">任务待处理</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {pendingTaskCount}
          </div>
        </div>
      </div>

      <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
        <label className="flex items-center gap-3 border border-[var(--line)] bg-white px-3 py-3 text-sm">
          <MagnifyingGlass size={16} className="text-[var(--text-soft)]" />
          <input
            className="w-full bg-transparent outline-none"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="按流程、任务、处理人、分类搜索"
          />
        </label>
        <div className="subtle-chip justify-center">
          先锁定异常实例，再处理积压任务和报表样本
        </div>
        <button
          aria-label="刷新监管数据"
          className="subtle-chip"
          type="button"
          onClick={() => {
            instanceQuery.refetch();
            taskQuery.refetch();
          }}
        >
          <ArrowsClockwise size={14} />
          刷新
        </button>
      </div>

      {monitorType !== 'tasks' ? (
        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <label className="flex items-center gap-3 border border-[var(--line)] bg-white px-3 py-3 text-sm">
            <span className="text-[var(--text-muted)]">管理员撤回原因</span>
            <input
              className="w-full bg-transparent outline-none"
              value={cancelReason}
              onChange={(event) => setCancelReason(event.target.value)}
              placeholder="请输入撤回说明"
            />
          </label>
          <div className="subtle-chip justify-center">
            承接 `/bpm/process-instance/cancel-by-admin`，仅在实例监管视图可用
          </div>
        </div>
      ) : null}

      {actionError ? (
        <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
          {actionError}
        </div>
      ) : null}

      {monitorType === 'tasks' ? (
        <>
          <div className="work-list border-b border-[var(--line)]">
            {filteredTaskRows.slice(0, 6).map((task) => (
              <div key={task.id} className="work-row">
                <div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {task.name}
                  </div>
                  <div className="mt-1 work-meta">
                    流程：{task.processInstance?.name || '-'}
                  </div>
                </div>
                <div className="text-sm text-[var(--text-muted)]">处理人</div>
                <div className="text-sm">{task.assigneeUser?.nickname || '-'}</div>
                <div>
                  <StatusPill status={task.status} />
                </div>
                <div className="text-sm text-[var(--text-muted)]">
                  {formatDateTime(task.createTime)}
                </div>
                <div className="text-right text-xs text-[var(--text-soft)]">
                  {task.processInstance?.categoryName || '任务'}
                </div>
              </div>
            ))}
            {filteredTaskRows.length === 0 ? (
              <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
                当前没有命中的任务记录。
              </div>
            ) : null}
          </div>

          <div className="overflow-x-auto">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>流程</th>
                  <th>处理人</th>
                  <th>发起人</th>
                  <th>状态</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody>
                {filteredTaskRows.map((task) => (
                  <tr key={task.id}>
                    <td>{task.name}</td>
                    <td>{task.processInstance?.name || '-'}</td>
                    <td>{task.assigneeUser?.nickname || '-'}</td>
                    <td>{task.processInstance?.startUser?.nickname || '-'}</td>
                    <td>
                      <StatusPill status={task.status} />
                    </td>
                    <td>{formatDateTime(task.createTime)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="work-list border-b border-[var(--line)]">
            {filteredInstanceRows.slice(0, 6).map((item) => (
              <div key={item.id} className="work-row">
                <div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {item.name}
                  </div>
                  <div className="mt-1 work-meta">
                    发起人：{item.startUser?.nickname || '-'} · 分类：
                    {item.categoryName || '-'}
                  </div>
                </div>
                <div className="text-sm text-[var(--text-muted)]">状态</div>
                <div>
                  <StatusPill status={item.status} />
                </div>
                <div className="text-sm text-[var(--text-muted)]">
                  {item.processDefinition?.name || '-'}
                </div>
                <div className="text-sm text-[var(--text-muted)]">
                  {formatDateTime(item.createTime)}
                </div>
                <div className="text-right">
                  <div className="text-xs text-[var(--text-soft)]">
                    {monitorType === 'reports' ? '报表样本' : '实例'}
                  </div>
                  <button
                    className="mt-2 subtle-chip"
                    disabled={cancelMutation.isPending}
                    type="button"
                    onClick={() => cancelMutation.mutate(item.id)}
                  >
                    {cancelMutation.isPending ? '撤回中...' : '管理员撤回'}
                  </button>
                </div>
              </div>
            ))}
            {filteredInstanceRows.length === 0 ? (
              <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
                当前没有命中的流程实例。
              </div>
            ) : null}
          </div>

          <div className="overflow-x-auto">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>流程</th>
                  <th>发起人</th>
                  <th>分类</th>
                  <th>状态</th>
                  <th>流程定义</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody>
                {filteredInstanceRows.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td>
                    <td>{item.startUser?.nickname || '-'}</td>
                    <td>{item.categoryName || '-'}</td>
                    <td>
                      <StatusPill status={item.status} />
                    </td>
                    <td>{item.processDefinition?.name || '-'}</td>
                    <td>
                      <div className="flex items-center justify-between gap-3">
                        <span>{formatDateTime(item.createTime)}</span>
                        <button
                          className="subtle-chip"
                          disabled={cancelMutation.isPending}
                          type="button"
                          onClick={() => cancelMutation.mutate(item.id)}
                        >
                          {cancelMutation.isPending ? '撤回中...' : '管理员撤回'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
