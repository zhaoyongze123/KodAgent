import { useQuery } from '@tanstack/react-query';
import { MagnifyingGlass } from '@phosphor-icons/react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { getMyProcessInstances } from '@/entities/process-instance/api/process-instance-api';
import { getTodoTasks } from '@/entities/task/api/task-api';
import { formatDateTime, formatDuration } from '@/shared/lib/format';
import { StatusPill } from '@/shared/ui/status-pill';

export function WorkspacePage() {
  const [keyword, setKeyword] = useState('');
  const todoQuery = useQuery({
    queryKey: ['todo-tasks', 'workspace'],
    queryFn: () => getTodoTasks({ pageNo: 1, pageSize: 10 }),
  });
  const initiatedQuery = useQuery({
    queryKey: ['my-processes', 'workspace'],
    queryFn: () => getMyProcessInstances({ pageNo: 1, pageSize: 6 }),
  });

  const todoTasks = todoQuery.data?.list || [];
  const filteredTodoTasks = useMemo(() => {
    if (!keyword.trim()) {
      return todoTasks;
    }
    const nextKeyword = keyword.trim().toLowerCase();
    return todoTasks.filter((task) =>
      JSON.stringify(task).toLowerCase().includes(nextKeyword),
    );
  }, [keyword, todoTasks]);
  const urgentTasks = filteredTodoTasks.slice(0, 4);
  const recentProcesses = initiatedQuery.data?.list || [];
  const timeoutTasks = filteredTodoTasks.filter(
    (task) => (task.durationInMillis || 0) >= 1000 * 60 * 60 * 24,
  );

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_360px]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">工作台</div>
            <h2>进入系统先处理待审批事项</h2>
          </div>
          <div className="inline-kpi">
            <strong>{filteredTodoTasks.length}</strong>
            <span>待处理任务</span>
          </div>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">紧急事项</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {urgentTasks.length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">超时事项</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {timeoutTasks.length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">最近发起</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {recentProcesses.length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">今日节奏</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">
              先清待办，再回看我发起和近期流转
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
              placeholder="按流程名、发起人、节点搜索待办"
            />
          </label>
          <Link className="subtle-chip justify-center" to="/center/todo">
            打开审批中心
          </Link>
          <button className="subtle-chip justify-center" type="button" onClick={() => {
            todoQuery.refetch();
            initiatedQuery.refetch();
          }}>
            刷新数据
          </button>
        </div>

        <div className="work-list border-b border-[var(--line)]">
          <div className="work-row bg-[var(--panel-muted)] text-xs font-medium text-[var(--text-soft)]">
            <div>流程 / 摘要</div>
            <div>发起人</div>
            <div>当前节点</div>
            <div>状态</div>
            <div>已耗时</div>
            <div>操作</div>
          </div>
          {filteredTodoTasks.map((task) => (
            <div key={task.id} className="work-row">
              <div className="min-w-0">
                <div className="truncate font-medium">
                  {task.processInstance?.name || task.name}
                </div>
                <div className="mt-1 work-meta">
                  {(task.processInstance?.categoryName || '未分类') +
                    ' · ' +
                    formatDateTime(task.createTime)}
                </div>
              </div>
              <div className="text-sm">{task.processInstance?.startUser?.nickname || '-'}</div>
              <div className="text-sm">{task.name}</div>
              <div>
                <StatusPill status={task.status} />
              </div>
              <div className="text-sm tabular-nums">
                {formatDuration(task.durationInMillis)}
              </div>
              <div>
                <Link
                  className="text-sm font-medium text-[var(--accent)]"
                  to={`/detail/${task.processInstanceId}${task.id ? `?taskId=${task.id}` : ''}`}
                >
                  立即处理
                </Link>
              </div>
            </div>
            ))}
          {filteredTodoTasks.length === 0 ? (
            <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
              当前没有命中的待办任务。
            </div>
          ) : null}
        </div>
      </section>

      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">辅助视图</div>
            <h3>紧急与最近</h3>
          </div>
        </div>

        <div className="detail-block">
          <div className="mb-3 text-sm font-medium">紧急处理</div>
          <div className="space-y-3">
            {urgentTasks.map((task) => (
              <Link
                key={task.id}
                className="block border-b border-[var(--line)] pb-3 last:border-b-0 last:pb-0"
                to={`/detail/${task.processInstanceId}${task.id ? `?taskId=${task.id}` : ''}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="truncate font-medium">{task.name}</div>
                  <StatusPill status={task.status} />
                </div>
                <div className="mt-2 text-sm text-[var(--text-muted)]">
                  {(task.processInstance?.startUser?.nickname || '-') +
                    ' · ' +
                    formatDuration(task.durationInMillis)}
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div className="detail-block">
          <div className="mb-3 text-sm font-medium">最近发起</div>
          <div className="space-y-3">
            {recentProcesses.map((item) => (
              <Link
                key={item.id}
                className="block border-b border-[var(--line)] pb-3 last:border-b-0 last:pb-0"
                to={`/detail/${item.id}`}
              >
                <div className="truncate font-medium">{item.name}</div>
                <div className="mt-2 flex items-center justify-between text-sm text-[var(--text-muted)]">
                  <span className="tabular-nums">{formatDateTime(item.createTime)}</span>
                  <StatusPill status={item.status} />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
