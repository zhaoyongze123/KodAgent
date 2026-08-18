import { useQuery } from '@tanstack/react-query';
import { MagnifyingGlass } from '@phosphor-icons/react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  getMyProcessInstances,
  getProcessInstanceCopyPage,
} from '@/entities/process-instance/api/process-instance-api';
import { getDoneTasks, getTodoTasks } from '@/entities/task/api/task-api';
import { formatDateTime, formatDuration } from '@/shared/lib/format';
import { StatusPill } from '@/shared/ui/status-pill';

const sectionMeta = {
  copied: { description: '抄送链路统一回到一个收件箱里处理。', title: '抄送我的' },
  done: { description: '已经处理完成的审批，适合回看和追踪。', title: '已办任务' },
  initiated: { description: '我发起的流程实例，统一看状态和进展。', title: '我发起的' },
  todo: { description: '高频处理区，按任务优先级集中完成审批。', title: '待办任务' },
};

export function ApprovalCenterPage() {
  const params = useParams();
  const section = (params.section || 'todo') as keyof typeof sectionMeta;
  const meta = sectionMeta[section] || sectionMeta.todo;
  const [keyword, setKeyword] = useState('');

  const todoQuery = useQuery({
    enabled: section === 'todo',
    queryKey: ['center', 'todo'],
    queryFn: () => getTodoTasks({ pageNo: 1, pageSize: 20 }),
  });
  const doneQuery = useQuery({
    enabled: section === 'done',
    queryKey: ['center', 'done'],
    queryFn: () => getDoneTasks({ pageNo: 1, pageSize: 20 }),
  });
  const initiatedQuery = useQuery({
    enabled: section === 'initiated',
    queryKey: ['center', 'initiated'],
    queryFn: () => getMyProcessInstances({ pageNo: 1, pageSize: 20 }),
  });
  const copiedQuery = useQuery({
    enabled: section === 'copied',
    queryKey: ['center', 'copied'],
    queryFn: () => getProcessInstanceCopyPage({ pageNo: 1, pageSize: 20 }),
  });

  const rows =
    section === 'todo'
      ? todoQuery.data?.list || []
      : section === 'done'
        ? doneQuery.data?.list || []
        : section === 'copied'
          ? copiedQuery.data?.list || []
          : initiatedQuery.data?.list || [];
  const filteredRows = useMemo(() => {
    if (!keyword.trim()) {
      return rows;
    }
    const nextKeyword = keyword.trim().toLowerCase();
    return rows.filter((row: any) =>
      JSON.stringify(row).toLowerCase().includes(nextKeyword),
    );
  }, [keyword, rows]);
  const timeoutCount = filteredRows.filter(
    (row: any) => (row.durationInMillis || 0) >= 1000 * 60 * 60 * 24,
  ).length;

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">审批中心</div>
          <h2>{meta.title}</h2>
        </div>
        <div className="shell-subtitle max-w-[420px] text-right text-pretty">
          {meta.description}
        </div>
      </div>

      <div className="border-b border-[var(--line)] px-5 py-4">
        <div className="flex flex-wrap gap-2">
          {Object.entries(sectionMeta).map(([key, item]) => (
            <Link
              key={key}
              className={
                key === section
                  ? 'subtle-chip border-[var(--line-strong)] bg-white text-[var(--text)]'
                  : 'subtle-chip bg-[var(--panel-muted)] text-[var(--text-muted)]'
              }
              to={`/center/${key}`}
            >
              {item.title}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">当前分区</div>
          <div className="mt-2 text-lg font-semibold">{meta.title}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">结果数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {filteredRows.length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">超时事项</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{timeoutCount}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">处理重点</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            {section === 'todo'
              ? '优先完成待办'
              : section === 'done'
                ? '回看历史处理'
                : '追踪流程进展'}
          </div>
        </div>
      </div>

      <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
        <label className="flex items-center gap-3 border border-[var(--line)] bg-white px-3 py-3 text-sm">
          <MagnifyingGlass size={16} className="text-[var(--text-soft)]" />
          <input
            className="w-full bg-transparent outline-none"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="按流程名、发起人、节点、分类搜索"
          />
        </label>
        <button
          className="subtle-chip justify-center"
          type="button"
          onClick={() => {
            todoQuery.refetch();
            doneQuery.refetch();
            initiatedQuery.refetch();
            copiedQuery.refetch();
          }}
        >
          刷新数据
        </button>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {filteredRows.slice(0, 6).map((row: any) => {
          const processInstance =
            section === 'copied'
              ? {
                  categoryName: row.summary?.[0]?.key || '抄送',
                  createTime: row.processInstanceStartTime || row.createTime,
                  id: row.processInstanceId,
                  name: row.processInstanceName,
                  startUser: row.startUser,
                  status: undefined,
                }
              : row.processInstance || row;
          const processInstanceId = String(processInstance.id || row.processInstanceId || '');
          return (
            <div key={`${section}-digest-${row.id}`} className="work-row">
              <div>
                <div className="font-medium">{processInstance.name || row.name}</div>
                <div className="mt-1 work-meta">
                  {(processInstance.categoryName || '-') +
                    ' · ' +
                    formatDateTime(row.createTime || processInstance.createTime)}
                </div>
              </div>
              <div className="text-sm text-[var(--text-muted)]">
                {processInstance.startUser?.nickname || '-'}
              </div>
              <div className="text-sm">
                {section === 'copied'
                  ? row.activityName || row.reason || '-'
                  : row.name || processInstance.tasks?.[0]?.name || '-'}
              </div>
              <div>
                {section === 'copied' ? '-' : (
                  <StatusPill status={row.status || processInstance.status} />
                )}
              </div>
              <div className="text-sm tabular-nums">
                {section === 'copied' ? '-' : formatDuration(row.durationInMillis)}
              </div>
              <div>
                <Link
                  className="text-sm font-medium text-[var(--accent)]"
                  to={`/detail/${processInstanceId}${row.id ? `?taskId=${row.id}` : ''}`}
                >
                  查看详情
                </Link>
              </div>
            </div>
          );
        })}
        {filteredRows.length === 0 ? (
          <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
            当前分区没有命中记录。
          </div>
        ) : null}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>流程名称</th>
              <th>发起人</th>
              <th>当前节点</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>耗时</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row: any) => {
              const processInstance =
                section === 'copied'
                  ? {
                      categoryName: row.summary?.[0]?.key || '抄送',
                      createTime: row.processInstanceStartTime || row.createTime,
                      id: row.processInstanceId,
                      name: row.processInstanceName,
                      startUser: row.startUser,
                      status: undefined,
                    }
                  : row.processInstance || row;
              const processInstanceId = String(processInstance.id || row.processInstanceId || '');
              return (
                <tr key={`${section}-${row.id}`}>
                  <td>
                    <div className="font-medium">{processInstance.name || row.name}</div>
                    <div className="mt-1 text-xs text-[var(--text-muted)]">
                      {processInstance.categoryName || '-'}
                    </div>
                  </td>
                  <td>{processInstance.startUser?.nickname || '-'}</td>
                  <td>
                    {section === 'copied'
                      ? row.activityName || row.reason || '-'
                      : row.name || processInstance.tasks?.[0]?.name || '-'}
                  </td>
                  <td>
                    {section === 'copied' ? '-' : (
                      <StatusPill status={row.status || processInstance.status} />
                    )}
                  </td>
                  <td className="tabular-nums">
                    {formatDateTime(row.createTime || processInstance.createTime)}
                  </td>
                  <td className="tabular-nums">
                    {section === 'copied' ? '-' : formatDuration(row.durationInMillis)}
                  </td>
                  <td>
                    <Link
                      className="text-sm font-medium text-[var(--accent)]"
                      to={`/detail/${processInstanceId}${row.id ? `?taskId=${row.id}` : ''}`}
                    >
                      查看详情
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
