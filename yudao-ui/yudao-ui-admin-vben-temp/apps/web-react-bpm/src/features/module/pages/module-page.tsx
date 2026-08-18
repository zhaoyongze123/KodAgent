import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowsClockwise, MagnifyingGlass } from '@phosphor-icons/react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { http, type PageResult } from '@/shared/api/http';
import {
  moduleRegistry,
  navSections,
  type ModuleConfig,
} from '@/shared/config/module-registry';
import { formatDateTime } from '@/shared/lib/format';

function renderCellValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否';
  }
  if (typeof value === 'string' && value.includes('T') && value.includes(':')) {
    return formatDateTime(value);
  }
  return String(value);
}

function flattenTreeRows(
  rows: Record<string, unknown>[],
  level = 0,
): Array<Record<string, unknown> & { __level: number }> {
  return rows.flatMap((row) => {
    const children = Array.isArray(row.children)
      ? (row.children as Record<string, unknown>[])
      : [];
    return [
      { ...row, __level: level },
      ...flattenTreeRows(children, level + 1),
    ];
  });
}

async function queryModuleList(module: ModuleConfig) {
  if (!module.listPath) {
    return { list: [], total: 0 } as PageResult<Record<string, unknown>>;
  }
  if (module.listMode === 'list') {
    const list = await http.get<Record<string, unknown>[]>(module.listPath);
    return { list, total: list.length };
  }
  return http.get<PageResult<Record<string, unknown>>>(module.listPath, {
    params: { pageNo: 1, pageSize: 50 },
  });
}

function countTruthyValues(rows: Record<string, unknown>[], key?: string) {
  if (!key) {
    return 0;
  }
  return rows.filter((row) => Boolean(row[key])).length;
}

function downloadBlobFile(blob: Blob, fileName: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function NotifyMessageWorkspace() {
  const [selectedUnreadIds, setSelectedUnreadIds] = useState<number[]>([]);
  const [actionError, setActionError] = useState('');
  const pageQuery = useQuery({
    queryKey: ['module-special', 'notify-message', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/notify-message/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const unreadCountQuery = useQuery({
    queryKey: ['module-special', 'notify-message', 'unread-count'],
    queryFn: () => http.get<number>('/system/notify-message/get-unread-count'),
  });
  const unreadListQuery = useQuery({
    queryKey: ['module-special', 'notify-message', 'unread-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/notify-message/get-unread-list'),
  });
  const myPageQuery = useQuery({
    queryKey: ['module-special', 'notify-message', 'my-page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/notify-message/my-page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = pageQuery.data?.list || [];
  const unreadRows = unreadListQuery.data || [];
  const myRows = myPageQuery.data?.list || [];

  useEffect(() => {
    setSelectedUnreadIds(
      unreadRows
        .filter((row) => !row.readStatus)
        .slice(0, 5)
        .map((row) => Number(row.id))
        .filter(Boolean),
    );
  }, [unreadRows]);

  const markReadMutation = useMutation({
    mutationFn: async () => {
      if (selectedUnreadIds.length === 0) {
        throw new Error('请先选择需要标记已读的消息');
      }
      return http.put<boolean>('/system/notify-message/update-read', {}, {
        params: { ids: selectedUnreadIds.join(',') },
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '标记已读失败');
    },
    onSuccess: async () => {
      setActionError('');
      await Promise.all([
        pageQuery.refetch(),
        unreadCountQuery.refetch(),
        unreadListQuery.refetch(),
        myPageQuery.refetch(),
      ]);
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: async () => http.put<boolean>('/system/notify-message/update-all-read'),
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '全部已读失败');
    },
    onSuccess: async () => {
      setActionError('');
      await Promise.all([
        pageQuery.refetch(),
        unreadCountQuery.refetch(),
        unreadListQuery.refetch(),
        myPageQuery.refetch(),
      ]);
    },
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">消息中心</div>
          <h2>站内信消息</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => {
          pageQuery.refetch();
          unreadCountQuery.refetch();
          unreadListQuery.refetch();
        }}>
          <ArrowsClockwise size={14} />
          刷新消息
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">消息总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">未读消息</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {unreadCountQuery.data || 0}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">来源接口</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/notify-message/*</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">处理方式</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">先清未读，再回看全量消息记录</div>
        </div>
      </div>

      <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
        <div className="shell-subtitle text-pretty">
          除了看全量消息台账，还要承接当前用户自己的站内信分页与已读动作，避免读完消息还要跳回别的入口处理。
        </div>
        <button
          className="subtle-chip"
          disabled={markReadMutation.isPending}
          type="button"
          onClick={() => markReadMutation.mutate()}
        >
          {markReadMutation.isPending ? '处理中...' : '标记选中已读'}
        </button>
        <button
          className="subtle-chip"
          disabled={markAllReadMutation.isPending}
          type="button"
          onClick={() => markAllReadMutation.mutate()}
        >
          {markAllReadMutation.isPending ? '处理中...' : '全部标为已读'}
        </button>
      </div>

      {actionError ? (
        <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
          {actionError}
        </div>
      ) : null}

      <div className="work-list border-b border-[var(--line)]">
        {unreadRows.slice(0, 6).map((row, index) => (
          <div key={`notify-unread-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.templateCode)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.templateNickname)} · {renderCellValue(row.createTime)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">内容摘要</div>
            <div className="col-span-2 text-sm">{renderCellValue(row.templateContent)}</div>
            <div className="text-sm">{renderCellValue(row.readStatus ? '已读' : '未读')}</div>
            <div className="text-right">
              <label className="inline-flex items-center gap-2 text-xs text-[var(--text-soft)]">
                <input
                  checked={selectedUnreadIds.includes(Number(row.id))}
                  type="checkbox"
                  onChange={(event) => {
                    const rowId = Number(row.id);
                    setSelectedUnreadIds((current) =>
                      event.target.checked
                        ? [...current, rowId]
                        : current.filter((item) => item !== rowId),
                    );
                  }}
                />
                选中
              </label>
            </div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border-b border-[var(--line)]">
        <table className="dense-table">
          <thead>
            <tr>
              <th>我的消息</th>
              <th>模板编码</th>
              <th>发送时间</th>
              <th>已读</th>
            </tr>
          </thead>
          <tbody>
            {myRows.map((row, index) => (
              <tr key={`notify-my-row-${index}`}>
                <td>{renderCellValue(row.templateContent)}</td>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.createTime)}</td>
                <td>{renderCellValue(row.readStatus ? '已读' : '未读')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>模板编码</th>
              <th>发送人</th>
              <th>模板类型</th>
              <th>已读</th>
              <th>发送时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`notify-row-${index}`}>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.templateNickname)}</td>
                <td>{renderCellValue(row.templateType)}</td>
                <td>{renderCellValue(row.readStatus ? '已读' : '未读')}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function JobWorkspace() {
  const jobQuery = useQuery({
    queryKey: ['module-special', 'infra-job', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/job/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const jobLogQuery = useQuery({
    queryKey: ['module-special', 'infra-job-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/job-log/page', {
        params: { pageNo: 1, pageSize: 10 },
      }),
  });
  const jobs = jobQuery.data?.list || [];
  const logs = jobLogQuery.data?.list || [];
  const runningJobs = jobs.filter((row) => Number(row.status) === 1).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/infra/job/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'infra-job.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">运维监管</div>
          <h2>定时任务</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出任务'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => {
            jobQuery.refetch();
            jobLogQuery.refetch();
          }}>
            <ArrowsClockwise size={14} />
            刷新任务
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">任务总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{jobs.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用中</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{runningJobs}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">最近执行日志</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{logs.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">监管重点</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">关注状态、Cron 与最近执行结果</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {jobs.slice(0, 6).map((row, index) => (
          <div key={`job-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.handlerName)} · {renderCellValue(row.handlerParam)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">Cron</div>
            <div className="text-sm">{renderCellValue(row.cronExpression)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue((row.nextTimes as unknown[] | undefined)?.[0] || '-')}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">任务</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border-b border-[var(--line)]">
        <table className="dense-table">
          <thead>
            <tr>
              <th>任务名称</th>
              <th>处理器</th>
              <th>Cron</th>
              <th>状态</th>
              <th>重试次数</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((row, index) => (
              <tr key={`job-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.handlerName)}</td>
                <td>{renderCellValue(row.cronExpression)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.retryCount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>任务 ID</th>
              <th>处理器</th>
              <th>开始时间</th>
              <th>耗时</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((row, index) => (
              <tr key={`job-log-${index}`}>
                <td>{renderCellValue(row.jobId)}</td>
                <td>{renderCellValue(row.handlerName)}</td>
                <td>{renderCellValue(row.beginTime)}</td>
                <td>{renderCellValue(row.duration)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CodegenWorkspace() {
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const [activePreviewPath, setActivePreviewPath] = useState('');
  const [actionError, setActionError] = useState('');
  const codegenQuery = useQuery({
    queryKey: ['module-special', 'infra-codegen', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/codegen/table/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const schemaQuery = useQuery({
    queryKey: ['module-special', 'infra-codegen', 'schema-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/infra/codegen/db/table/list'),
  });
  const detailQuery = useQuery({
    queryKey: ['module-special', 'infra-codegen', 'detail', selectedTableId],
    queryFn: () =>
      http.get<{
        columns: Record<string, unknown>[];
        table: Record<string, unknown>;
      }>('/infra/codegen/detail', {
        params: { tableId: selectedTableId },
      }),
    enabled: selectedTableId !== null,
  });
  const previewQuery = useQuery({
    queryKey: ['module-special', 'infra-codegen', 'preview', selectedTableId],
    queryFn: () =>
      http.get<Array<{ code: string; filePath: string }>>('/infra/codegen/preview', {
        params: { tableId: selectedTableId },
      }),
    enabled: selectedTableId !== null,
  });
  const rows = codegenQuery.data?.list || [];
  const schemaRows = schemaQuery.data || [];
  const selectedRow =
    rows.find((row) => Number(row.id) === selectedTableId) || rows[0] || null;
  const detailTable = detailQuery.data?.table || null;
  const detailColumns = detailQuery.data?.columns || [];
  const previewFiles = previewQuery.data || [];
  const activePreview =
    previewFiles.find((item) => item.filePath === activePreviewPath) || previewFiles[0] || null;
  const dataSourceCount = new Set(
    rows.map((row) => String(row.dataSourceConfigId || '')).filter(Boolean),
  ).size;

  useEffect(() => {
    if (!selectedTableId && rows[0]?.id) {
      setSelectedTableId(Number(rows[0].id));
    }
  }, [rows, selectedTableId]);

  useEffect(() => {
    if (previewFiles.length === 0) {
      setActivePreviewPath('');
      return;
    }
    if (!previewFiles.some((item) => item.filePath === activePreviewPath)) {
      setActivePreviewPath(previewFiles[0]?.filePath || '');
    }
  }, [activePreviewPath, previewFiles]);

  const syncMutation = useMutation({
    mutationFn: async (tableId: number) =>
      http.put<boolean>('/infra/codegen/sync-from-db', {}, { params: { tableId } }),
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '同步失败');
    },
    onSuccess: async () => {
      setActionError('');
      await Promise.all([
        codegenQuery.refetch(),
        detailQuery.refetch(),
        previewQuery.refetch(),
        schemaQuery.refetch(),
      ]);
    },
  });

  const downloadMutation = useMutation({
    mutationFn: async (tableId: number) =>
      http.download('/infra/codegen/download', { params: { tableId } }),
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '下载失败');
    },
    onSuccess: (blob) => {
      setActionError('');
      const className = String(selectedRow?.className || selectedRow?.tableName || 'codegen');
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `codegen-${className}.zip`;
      link.click();
      window.URL.revokeObjectURL(url);
    },
  });

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.9fr)]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">研发工具</div>
            <h2>代码生成工作台</h2>
          </div>
          <button
            className="subtle-chip"
            type="button"
            onClick={() => {
              setActionError('');
              codegenQuery.refetch();
              schemaQuery.refetch();
            }}
          >
            <ArrowsClockwise size={14} />
            刷新生成表
          </button>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">生成表数量</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">模块覆盖</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {new Set(rows.map((row) => String(row.moduleName || '')).filter(Boolean)).size}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">数据源</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{dataSourceCount}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">数据库表</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{schemaRows.length}</div>
          </div>
        </div>

        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="shell-subtitle text-pretty">
            在一个工作面里完成表清单浏览、字段核对、代码预览、结构同步和 ZIP 下载，不再跳回旧式弹窗后台。
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="subtle-chip">/infra/codegen/table/page</span>
            <span className="subtle-chip">/infra/codegen/detail</span>
            <span className="subtle-chip">/infra/codegen/preview</span>
            <span className="subtle-chip">/infra/codegen/download</span>
          </div>
        </div>

        <div className="work-list border-b border-[var(--line)]">
          {rows.slice(0, 8).map((row, index) => {
            const rowId = Number(row.id || 0);
            const active = rowId === selectedTableId;
            return (
              <button
                key={`codegen-row-${index}`}
                className={active ? 'work-row bg-[#f7fafc] text-left' : 'work-row text-left'}
                type="button"
                onClick={() => {
                  setActionError('');
                  setSelectedTableId(rowId);
                }}
              >
                <div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {renderCellValue(row.tableName)}
                  </div>
                  <div className="mt-1 work-meta">
                    {renderCellValue(row.tableComment)} · {renderCellValue(row.className)}
                  </div>
                </div>
                <div className="text-sm text-[var(--text-muted)]">模块</div>
                <div className="text-sm">{renderCellValue(row.moduleName)}</div>
                <div className="text-sm">{renderCellValue(row.businessName)}</div>
                <div className="text-sm text-[var(--text-muted)]">{renderCellValue(row.author)}</div>
                <div className="text-right text-xs text-[var(--text-soft)]">
                  {active ? '当前处理' : `#${index + 1}`}
                </div>
              </button>
            );
          })}
        </div>

        <div className="overflow-x-auto border-b border-[var(--line)]">
          <table className="dense-table">
            <thead>
              <tr>
                <th>表名</th>
                <th>表说明</th>
                <th>模块名</th>
                <th>业务名</th>
                <th>类名</th>
                <th>作者</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={`codegen-table-${index}`}
                  className={Number(row.id) === selectedTableId ? 'bg-[#f7fafc]' : undefined}
                >
                  <td>{renderCellValue(row.tableName)}</td>
                  <td>{renderCellValue(row.tableComment)}</td>
                  <td>{renderCellValue(row.moduleName)}</td>
                  <td>{renderCellValue(row.businessName)}</td>
                  <td>{renderCellValue(row.className)}</td>
                  <td>{renderCellValue(row.author)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="overflow-x-auto">
          <table className="dense-table">
            <thead>
              <tr>
                <th>数据库表</th>
                <th>表备注</th>
              </tr>
            </thead>
            <tbody>
              {schemaRows.slice(0, 10).map((row, index) => (
                <tr key={`codegen-schema-${index}`}>
                  <td>{renderCellValue(row.name)}</td>
                  <td>{renderCellValue(row.comment)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">当前处理台</div>
            <h2>{renderCellValue(selectedRow?.tableName || '请选择生成表')}</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="subtle-chip"
              disabled={!selectedTableId || syncMutation.isPending}
              type="button"
              onClick={() => {
                if (selectedTableId) {
                  syncMutation.mutate(selectedTableId);
                }
              }}
            >
              <ArrowsClockwise size={14} />
              {syncMutation.isPending ? '同步中...' : '同步结构'}
            </button>
            <button
              className="subtle-chip"
              disabled={!selectedTableId || downloadMutation.isPending}
              type="button"
              onClick={() => {
                if (selectedTableId) {
                  downloadMutation.mutate(selectedTableId);
                }
              }}
            >
              {downloadMutation.isPending ? '生成中...' : '下载代码'}
            </button>
          </div>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-2">
          <div className="detail-block">
            <div className="work-meta">类名</div>
            <div className="mt-2 text-sm font-medium">{renderCellValue(detailTable?.className)}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">模板类型</div>
            <div className="mt-2 text-sm font-medium">
              {renderCellValue(detailTable?.templateType)}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">字段数量</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{detailColumns.length}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">数据源 ID</div>
            <div className="mt-2 text-sm font-medium">
              {renderCellValue(detailTable?.dataSourceConfigId)}
            </div>
          </div>
        </div>

        {actionError ? (
          <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-2 text-sm font-medium">生成配置摘要</div>
          <div className="grid gap-2 text-sm text-[var(--text-muted)]">
            <div>作者：{renderCellValue(detailTable?.author)}</div>
            <div>模块：{renderCellValue(detailTable?.moduleName)}</div>
            <div>业务：{renderCellValue(detailTable?.businessName)}</div>
            <div>场景：{renderCellValue(detailTable?.scene)}</div>
          </div>
        </div>

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium">字段定义</div>
            <div className="text-xs text-[var(--text-soft)]">
              {detailQuery.isLoading ? '正在加载字段...' : `${detailColumns.length} 个字段`}
            </div>
          </div>
          <div className="max-h-[220px] overflow-auto border border-[var(--line)]">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>字段</th>
                  <th>类型</th>
                  <th>Java 字段</th>
                </tr>
              </thead>
              <tbody>
                {detailColumns.slice(0, 12).map((column, index) => (
                  <tr key={`codegen-column-${index}`}>
                    <td>{renderCellValue(column.columnName)}</td>
                    <td>{renderCellValue(column.dataType)}</td>
                    <td>{renderCellValue(column.javaField)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium">预览文件</div>
            <div className="text-xs text-[var(--text-soft)]">
              {previewQuery.isLoading ? '正在生成预览...' : `${previewFiles.length} 个文件`}
            </div>
          </div>
          <div className="grid gap-2">
            <div className="flex flex-wrap gap-2">
              {previewFiles.slice(0, 10).map((file) => (
                <button
                  key={file.filePath}
                  className={
                    file.filePath === activePreview?.filePath
                      ? 'subtle-chip bg-white text-[var(--text)]'
                      : 'subtle-chip'
                  }
                  type="button"
                  onClick={() => setActivePreviewPath(file.filePath)}
                >
                  {file.filePath.split('/').pop()}
                </button>
              ))}
            </div>
            <div className="border border-[var(--line)] bg-[#fbfcfe]">
              <div className="border-b border-[var(--line)] px-4 py-2 text-xs text-[var(--text-soft)]">
                {activePreview?.filePath || '暂无可预览文件'}
              </div>
              <pre className="max-h-[320px] overflow-auto px-4 py-3 text-xs leading-6 text-[var(--text)]">
                <code>{activePreview?.code || '选择生成表后将在这里展示真实代码预览。'}</code>
              </pre>
            </div>
          </div>
        </div>

        <div className="px-5 py-4">
          <div className="mb-2 text-sm font-medium">后端接口映射</div>
          <div className="grid gap-2 text-xs text-[var(--text-muted)]">
            <div>/infra/codegen/detail?tableId=</div>
            <div>/infra/codegen/sync-from-db?tableId=</div>
            <div>/infra/codegen/preview?tableId=</div>
            <div>/infra/codegen/download?tableId=</div>
          </div>
        </div>
      </aside>
    </div>
  );
}

function MailTemplateWorkspace() {
  const [selectedTemplateCode, setSelectedTemplateCode] = useState('');
  const [toMails, setToMails] = useState('');
  const [ccMails, setCcMails] = useState('');
  const [bccMails, setBccMails] = useState('');
  const [templateParamsText, setTemplateParamsText] = useState('{}');
  const [actionError, setActionError] = useState('');
  const templateQuery = useQuery({
    queryKey: ['module-special', 'mail-template', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/mail-template/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const logQuery = useQuery({
    queryKey: ['module-special', 'mail-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/mail-log/page', {
        params: { pageNo: 1, pageSize: 10 },
      }),
  });
  const accountQuery = useQuery({
    queryKey: ['module-special', 'mail-account', 'simple-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/mail-account/simple-list'),
  });
  const templates = templateQuery.data?.list || [];
  const logs = logQuery.data?.list || [];
  const accounts = accountQuery.data || [];

  useEffect(() => {
    if (!selectedTemplateCode && templates[0]?.code) {
      setSelectedTemplateCode(String(templates[0].code));
    }
  }, [selectedTemplateCode, templates]);

  const sendMailMutation = useMutation({
    mutationFn: async () => {
      const templateParams = JSON.parse(templateParamsText || '{}') as Record<string, unknown>;
      return http.post<number>('/system/mail-template/send-mail', {
        bccMails: bccMails
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        ccMails: ccMails
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
        templateCode: selectedTemplateCode,
        templateParams,
        toMails: toMails
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean),
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '发送测试邮件失败');
    },
    onSuccess: async () => {
      setActionError('');
      await logQuery.refetch();
    },
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>邮件模板</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => {
          templateQuery.refetch();
          logQuery.refetch();
        }}>
          <ArrowsClockwise size={14} />
          刷新邮件
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">模板数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{templates.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">最近日志</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{logs.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">发信账号</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{accounts.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/mail-template/* + /system/mail-log/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {templates.slice(0, 6).map((row, index) => (
          <div key={`mail-template-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.code)} · {renderCellValue(row.nickname)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">标题</div>
            <div className="text-sm">{renderCellValue(row.title)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">模板</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border-b border-[var(--line)]">
        <table className="dense-table">
          <thead>
            <tr>
              <th>模板名称</th>
              <th>模板编码</th>
              <th>发送人</th>
              <th>标题</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((row, index) => (
              <tr key={`mail-template-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.nickname)}</td>
                <td>{renderCellValue(row.title)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>收件人</th>
              <th>模板编码</th>
              <th>标题</th>
              <th>发送状态</th>
              <th>发送时间</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((row, index) => (
              <tr key={`mail-log-${index}`}>
                <td>{renderCellValue(Array.isArray(row.toMails) ? row.toMails.join(', ') : row.toMails)}</td>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.templateTitle)}</td>
                <td>{renderCellValue(row.sendStatus)}</td>
                <td>{renderCellValue(row.sendTime || row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[var(--line)] px-5 py-4">
        <div className="mb-2 text-sm font-medium">发送测试能力</div>
        {actionError ? (
          <div className="mb-3 border border-[#efc3bd] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">模板编码</div>
            <select
              className="w-full bg-transparent outline-none"
              value={selectedTemplateCode}
              onChange={(event) => setSelectedTemplateCode(event.target.value)}
            >
              {templates.map((item, index) => (
                <option key={`mail-send-template-${index}`} value={String(item.code)}>
                  {renderCellValue(item.name)} · {renderCellValue(item.code)}
                </option>
              ))}
            </select>
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">主送邮箱</div>
            <input
              className="w-full bg-transparent outline-none"
              placeholder="多个邮箱用逗号分隔"
              value={toMails}
              onChange={(event) => setToMails(event.target.value)}
            />
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">抄送邮箱</div>
            <input
              className="w-full bg-transparent outline-none"
              placeholder="可选，多个邮箱用逗号分隔"
              value={ccMails}
              onChange={(event) => setCcMails(event.target.value)}
            />
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">密送邮箱</div>
            <input
              className="w-full bg-transparent outline-none"
              placeholder="可选，多个邮箱用逗号分隔"
              value={bccMails}
              onChange={(event) => setBccMails(event.target.value)}
            />
          </label>
        </div>
        <label className="mt-3 block border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
          <div className="mb-2 text-[var(--text-muted)]">模板参数 JSON</div>
          <textarea
            className="min-h-[120px] w-full bg-transparent outline-none"
            value={templateParamsText}
            onChange={(event) => setTemplateParamsText(event.target.value)}
          />
        </label>
        <div className="mt-3 flex items-center justify-between">
          <div className="text-xs text-[var(--text-muted)]">
            真实接口：`/system/mail-template/send-mail`
          </div>
          <button
            className="subtle-chip"
            disabled={sendMailMutation.isPending}
            type="button"
            onClick={() => sendMailMutation.mutate()}
          >
            {sendMailMutation.isPending ? '发送中...' : '发送测试邮件'}
          </button>
        </div>
      </div>
    </section>
  );
}

function SmsTemplateWorkspace() {
  const [selectedTemplateCode, setSelectedTemplateCode] = useState('');
  const [mobile, setMobile] = useState('');
  const [templateParamsText, setTemplateParamsText] = useState('{}');
  const [actionError, setActionError] = useState('');
  const templateQuery = useQuery({
    queryKey: ['module-special', 'sms-template', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/sms-template/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const logQuery = useQuery({
    queryKey: ['module-special', 'sms-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/sms-log/page', {
        params: { pageNo: 1, pageSize: 10 },
      }),
  });
  const channelQuery = useQuery({
    queryKey: ['module-special', 'sms-channel', 'simple-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/sms-channel/simple-list'),
  });
  const templates = templateQuery.data?.list || [];
  const logs = logQuery.data?.list || [];
  const channels = channelQuery.data || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/sms-template/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-sms-template.xlsx'),
  });

  useEffect(() => {
    if (!selectedTemplateCode && templates[0]?.code) {
      setSelectedTemplateCode(String(templates[0].code));
    }
  }, [selectedTemplateCode, templates]);

  const sendSmsMutation = useMutation({
    mutationFn: async () => {
      const templateParams = JSON.parse(templateParamsText || '{}') as Record<string, unknown>;
      return http.post<number>('/system/sms-template/send-sms', {
        mobile,
        templateCode: selectedTemplateCode,
        templateParams,
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '发送测试短信失败');
    },
    onSuccess: async () => {
      setActionError('');
      await logQuery.refetch();
    },
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>短信模板</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出模板'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => {
            templateQuery.refetch();
            logQuery.refetch();
          }}>
            <ArrowsClockwise size={14} />
            刷新短信
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">模板数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{templates.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">发送日志</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{logs.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">短信渠道</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{channels.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/sms-template/* + /system/sms-log/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {templates.slice(0, 6).map((row, index) => (
          <div key={`sms-template-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.code)} · {renderCellValue(row.channelCode)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">内容</div>
            <div className="text-sm">{renderCellValue(row.content)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">短信</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto border-b border-[var(--line)]">
        <table className="dense-table">
          <thead>
            <tr>
              <th>模板名称</th>
              <th>模板编码</th>
              <th>渠道</th>
              <th>状态</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((row, index) => (
              <tr key={`sms-template-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.channelCode)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>手机号</th>
              <th>模板编码</th>
              <th>发送状态</th>
              <th>渠道</th>
              <th>发送时间</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((row, index) => (
              <tr key={`sms-log-${index}`}>
                <td>{renderCellValue(row.mobile)}</td>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.sendStatus)}</td>
                <td>{renderCellValue(row.channelCode)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[var(--line)] px-5 py-4">
        <div className="mb-2 text-sm font-medium">发送测试能力</div>
        {actionError ? (
          <div className="mb-3 border border-[#efc3bd] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">模板编码</div>
            <select
              className="w-full bg-transparent outline-none"
              value={selectedTemplateCode}
              onChange={(event) => setSelectedTemplateCode(event.target.value)}
            >
              {templates.map((item, index) => (
                <option key={`sms-send-template-${index}`} value={String(item.code)}>
                  {renderCellValue(item.name)} · {renderCellValue(item.code)}
                </option>
              ))}
            </select>
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">手机号</div>
            <input
              className="w-full bg-transparent outline-none"
              placeholder="请输入测试手机号"
              value={mobile}
              onChange={(event) => setMobile(event.target.value)}
            />
          </label>
        </div>
        <label className="mt-3 block border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
          <div className="mb-2 text-[var(--text-muted)]">模板参数 JSON</div>
          <textarea
            className="min-h-[120px] w-full bg-transparent outline-none"
            value={templateParamsText}
            onChange={(event) => setTemplateParamsText(event.target.value)}
          />
        </label>
        <div className="mt-3 flex items-center justify-between">
          <div className="text-xs text-[var(--text-muted)]">
            真实接口：`/system/sms-template/send-sms`
          </div>
          <button
            className="subtle-chip"
            disabled={sendSmsMutation.isPending}
            type="button"
            onClick={() => sendSmsMutation.mutate()}
          >
            {sendSmsMutation.isPending ? '发送中...' : '发送测试短信'}
          </button>
        </div>
      </div>
    </section>
  );
}

function OAuth2TokenWorkspace() {
  const tokenQuery = useQuery({
    queryKey: ['module-special', 'oauth2-token', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/oauth2-token/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = tokenQuery.data?.list || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">认证体系</div>
          <h2>OAuth2 令牌</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => tokenQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新令牌
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">令牌数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">客户端数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.clientId || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/oauth2-token/page</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">工作方式</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">按用户、客户端和过期时间监管令牌</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`oauth2-token-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.clientId)}
              </div>
              <div className="mt-1 work-meta">
                用户 {renderCellValue(row.userId)} · 类型 {renderCellValue(row.userType)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">访问令牌</div>
            <div className="text-sm">{renderCellValue(row.accessToken)}</div>
            <div className="text-sm">{renderCellValue(row.refreshToken)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.expiresTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">令牌</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>Client ID</th>
              <th>用户 ID</th>
              <th>用户类型</th>
              <th>签发时间</th>
              <th>到期时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`oauth2-token-table-${index}`}>
                <td>{renderCellValue(row.clientId)}</td>
                <td>{renderCellValue(row.userId)}</td>
                <td>{renderCellValue(row.userType)}</td>
                <td>{renderCellValue(row.createTime)}</td>
                <td>{renderCellValue(row.expiresTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function NotifyTemplateWorkspace() {
  const [selectedTemplateCode, setSelectedTemplateCode] = useState('');
  const [notifyUserId, setNotifyUserId] = useState('');
  const [notifyUserType, setNotifyUserType] = useState('2');
  const [templateParamsText, setTemplateParamsText] = useState('{}');
  const [actionError, setActionError] = useState('');
  const templateQuery = useQuery({
    queryKey: ['module-special', 'notify-template', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/notify-template/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const templates = templateQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/notify-template/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-notify-template.xlsx'),
  });

  useEffect(() => {
    if (!selectedTemplateCode && templates[0]?.code) {
      setSelectedTemplateCode(String(templates[0].code));
    }
  }, [selectedTemplateCode, templates]);

  const sendNotifyMutation = useMutation({
    mutationFn: async () => {
      const templateParams = JSON.parse(templateParamsText || '{}') as Record<string, unknown>;
      return http.post<number>('/system/notify-template/send-notify', {
        templateCode: selectedTemplateCode,
        templateParams,
        userId: Number(notifyUserId),
        userType: Number(notifyUserType),
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '发送站内信失败');
    },
    onSuccess: async () => {
      setActionError('');
    },
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">消息中心</div>
          <h2>站内信模板</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出模板'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => templateQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新模板
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">模板数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{templates.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用模板</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {templates.filter((row) => Number(row.status) === 0 || Number(row.status) === 1).length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">动态参数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {templates.reduce(
              (sum, row) => sum + (Array.isArray(row.params) ? row.params.length : 0),
              0,
            )}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/notify-template/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {templates.slice(0, 6).map((row, index) => (
          <div key={`notify-template-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.code)} · {renderCellValue(row.nickname)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">内容</div>
            <div className="text-sm">{renderCellValue(row.content)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">{renderCellValue(row.remark)}</div>
            <div className="text-right text-xs text-[var(--text-soft)]">站内信</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>模板名称</th>
              <th>模板编码</th>
              <th>发送人</th>
              <th>状态</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((row, index) => (
              <tr key={`notify-template-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.nickname)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.remark)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-[var(--line)] px-5 py-4">
        <div className="mb-2 text-sm font-medium">发送测试能力</div>
        {actionError ? (
          <div className="mb-3 border border-[#efc3bd] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-3">
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">模板编码</div>
            <select
              className="w-full bg-transparent outline-none"
              value={selectedTemplateCode}
              onChange={(event) => setSelectedTemplateCode(event.target.value)}
            >
              {templates.map((item, index) => (
                <option key={`notify-send-template-${index}`} value={String(item.code)}>
                  {renderCellValue(item.name)} · {renderCellValue(item.code)}
                </option>
              ))}
            </select>
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">接收人 ID</div>
            <input
              className="w-full bg-transparent outline-none"
              placeholder="请输入管理员或会员 ID"
              value={notifyUserId}
              onChange={(event) => setNotifyUserId(event.target.value)}
            />
          </label>
          <label className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
            <div className="mb-2 text-[var(--text-muted)]">接收人类型</div>
            <select
              className="w-full bg-transparent outline-none"
              value={notifyUserType}
              onChange={(event) => setNotifyUserType(event.target.value)}
            >
              <option value="1">会员</option>
              <option value="2">管理员</option>
            </select>
          </label>
        </div>
        <label className="mt-3 block border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
          <div className="mb-2 text-[var(--text-muted)]">模板参数 JSON</div>
          <textarea
            className="min-h-[120px] w-full bg-transparent outline-none"
            value={templateParamsText}
            onChange={(event) => setTemplateParamsText(event.target.value)}
          />
        </label>
        <div className="mt-3 flex items-center justify-between">
          <div className="text-xs text-[var(--text-muted)]">
            真实接口：`/system/notify-template/send-notify`
          </div>
          <button
            className="subtle-chip"
            disabled={sendNotifyMutation.isPending}
            type="button"
            onClick={() => sendNotifyMutation.mutate()}
          >
            {sendNotifyMutation.isPending ? '发送中...' : '发送站内信测试'}
          </button>
        </div>
      </div>
    </section>
  );
}

function RedisWorkspace() {
  const redisQuery = useQuery({
    queryKey: ['module-special', 'infra-redis', 'monitor'],
    queryFn: () =>
      http.get<{
        commandStats?: Array<Record<string, unknown>>;
        dbSize?: number;
        info?: Record<string, unknown>;
      }>('/infra/redis/get-monitor-info'),
  });
  const info = redisQuery.data?.info || {};
  const commandStats = redisQuery.data?.commandStats || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">缓存监控</div>
          <h2>Redis 监控</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => redisQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新监控
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">DB 大小</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {renderCellValue(redisQuery.data?.dbSize)}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">Redis 版本</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {renderCellValue(info.redis_version)}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">已用内存</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {renderCellValue(info.used_memory_human)}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">QPS</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {renderCellValue(info.instantaneous_ops_per_sec)}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto border-b border-[var(--line)]">
        <table className="dense-table">
          <thead>
            <tr>
              <th>指标</th>
              <th>值</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['role', info.role],
              ['connected_clients', info.connected_clients],
              ['uptime_in_days', info.uptime_in_days],
              ['used_memory_peak_human', info.used_memory_peak_human],
              ['mem_fragmentation_ratio', info.mem_fragmentation_ratio],
            ].map(([key, value]) => (
              <tr key={String(key)}>
                <td>{String(key)}</td>
                <td>{renderCellValue(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>命令</th>
              <th>调用次数</th>
              <th>耗时</th>
            </tr>
          </thead>
          <tbody>
            {commandStats.map((row, index) => (
              <tr key={`redis-command-${index}`}>
                <td>{renderCellValue(row.command)}</td>
                <td>{renderCellValue(row.calls)}</td>
                <td>{renderCellValue(row.usec)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MailLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'mail-log', 'full-page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/mail-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const logs = logQuery.data?.list || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>邮件日志</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新日志
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">日志数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{logs.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">发送成功</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {logs.filter((row) => Number(row.sendStatus) === 10 || Number(row.sendStatus) === 0).length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">模板覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(logs.map((row) => String(row.templateCode || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">工作方式</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">按收件人、模板和异常原因回看发送结果</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {logs.slice(0, 6).map((row, index) => (
          <div key={`mail-log-digest-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(Array.isArray(row.toMails) ? row.toMails.join(', ') : row.toMails)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.templateCode)} · {renderCellValue(row.templateTitle)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">发送状态</div>
            <div className="text-sm">{renderCellValue(row.sendStatus)}</div>
            <div className="text-sm">{renderCellValue(row.sendTime || row.createTime)}</div>
            <div className="text-sm text-[var(--text-muted)]">{renderCellValue(row.sendException)}</div>
            <div className="text-right text-xs text-[var(--text-soft)]">日志</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>收件人</th>
              <th>模板编码</th>
              <th>模板标题</th>
              <th>发送状态</th>
              <th>发送时间</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((row, index) => (
              <tr key={`mail-log-table-${index}`}>
                <td>{renderCellValue(Array.isArray(row.toMails) ? row.toMails.join(', ') : row.toMails)}</td>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.templateTitle)}</td>
                <td>{renderCellValue(row.sendStatus)}</td>
                <td>{renderCellValue(row.sendTime || row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ConfigWorkspace() {
  const configQuery = useQuery({
    queryKey: ['module-special', 'infra-config', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/config/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = configQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/infra/config/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'infra-config.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">基础设施</div>
          <h2>参数配置</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出参数'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => configQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新参数
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">参数数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">分类数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.category || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">公开可见</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {rows.filter((row) => Boolean(row.visible)).length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">工作方式</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">按分类、键名和值统一管理系统参数</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`config-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.category)} · {renderCellValue(row.key)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">参数值</div>
            <div className="text-sm">{renderCellValue(row.value)}</div>
            <div className="text-sm">{renderCellValue(row.visible ? '可见' : '隐藏')}</div>
            <div className="text-sm text-[var(--text-muted)]">{renderCellValue(row.remark)}</div>
            <div className="text-right text-xs text-[var(--text-soft)]">配置</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>参数名称</th>
              <th>分类</th>
              <th>键名</th>
              <th>值</th>
              <th>可见</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`config-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.category)}</td>
                <td>{renderCellValue(row.key)}</td>
                <td>{renderCellValue(row.value)}</td>
                <td>{renderCellValue(row.visible ? '可见' : '隐藏')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DataSourceWorkspace() {
  const query = useQuery({
    queryKey: ['module-special', 'infra-data-source-config', 'list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/infra/data-source-config/list'),
  });
  const rows = query.data || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">基础设施</div>
          <h2>数据源配置</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => query.refetch()}>
          <ArrowsClockwise size={14} />
          刷新数据源
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">数据源数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">用户名覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.username || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/infra/data-source-config/list</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">工作方式</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">统一管理代码生成与多数据源连接</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`ds-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.username)} · {renderCellValue(row.createTime)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">连接地址</div>
            <div className="col-span-2 text-sm">{renderCellValue(row.url)}</div>
            <div className="text-sm">{renderCellValue(row.username)}</div>
            <div className="text-right text-xs text-[var(--text-soft)]">数据源</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>连接地址</th>
              <th>用户名</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`ds-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.url)}</td>
                <td>{renderCellValue(row.username)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MailAccountWorkspace() {
  const accountQuery = useQuery({
    queryKey: ['module-special', 'mail-account', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/mail-account/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = accountQuery.data?.list || [];
  const enabledRows = rows.filter((row) => Number(row.status) === 0).length;
  const sslRows = rows.filter(
    (row) => Boolean(row.sslEnable) || Boolean(row.starttlsEnable),
  ).length;

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>邮箱账号</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => accountQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新账号
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">账号数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用账号</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{enabledRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">加密传输</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{sslRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/mail-account/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`mail-account-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.mail)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.username)} · {renderCellValue(row.host)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">端口</div>
            <div className="text-sm">{renderCellValue(row.port)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(
                row.sslEnable ? 'SSL' : row.starttlsEnable ? 'STARTTLS' : '明文',
              )}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">账号</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>邮箱</th>
              <th>用户名</th>
              <th>主机</th>
              <th>端口</th>
              <th>SSL / TLS</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`mail-account-table-${index}`}>
                <td>{renderCellValue(row.mail)}</td>
                <td>{renderCellValue(row.username)}</td>
                <td>{renderCellValue(row.host)}</td>
                <td>{renderCellValue(row.port)}</td>
                <td>
                  {renderCellValue(
                    row.sslEnable ? 'SSL' : row.starttlsEnable ? 'STARTTLS' : '明文',
                  )}
                </td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SmsChannelWorkspace() {
  const channelQuery = useQuery({
    queryKey: ['module-special', 'sms-channel', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/sms-channel/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = channelQuery.data?.list || [];
  const enabledRows = rows.filter((row) => Number(row.status) === 0).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/sms-channel/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-sms-channel.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>短信渠道</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出渠道'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => channelQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新渠道
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">渠道数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用渠道</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{enabledRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">签名数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.signature || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/sms-channel/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`sms-channel-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.signature)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.code)} · {renderCellValue(row.apiKey)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">回调地址</div>
            <div className="text-sm">{renderCellValue(row.callbackUrl)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">渠道</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>签名</th>
              <th>渠道编码</th>
              <th>API Key</th>
              <th>回调地址</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`sms-channel-table-${index}`}>
                <td>{renderCellValue(row.signature)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.apiKey)}</td>
                <td>{renderCellValue(row.callbackUrl)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OAuth2ClientWorkspace() {
  const clientQuery = useQuery({
    queryKey: ['module-special', 'oauth2-client', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/oauth2-client/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = clientQuery.data?.list || [];
  const autoApproveRows = countTruthyValues(rows, 'autoApprove');

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">认证体系</div>
          <h2>OAuth2 客户端</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => clientQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新客户端
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">客户端数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">自动授权</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {autoApproveRows}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">授权方式种类</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {
              new Set(
                rows.flatMap((row) =>
                  Array.isArray(row.authorizedGrantTypes)
                    ? row.authorizedGrantTypes.map((item) => String(item))
                    : [],
                ),
              ).size
            }
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/oauth2-client/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`oauth2-client-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.clientId)} · {renderCellValue(row.secret)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">回调地址</div>
            <div className="text-sm">
              {renderCellValue(
                Array.isArray(row.redirectUris)
                  ? row.redirectUris.join(', ')
                  : row.redirectUris,
              )}
            </div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.autoApprove ? '自动授权' : '显式确认')}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">客户端</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>Client ID</th>
              <th>授权方式</th>
              <th>Scope</th>
              <th>自动授权</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`oauth2-client-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.clientId)}</td>
                <td>
                  {renderCellValue(
                    Array.isArray(row.authorizedGrantTypes)
                      ? row.authorizedGrantTypes.join(', ')
                      : row.authorizedGrantTypes,
                  )}
                </td>
                <td>
                  {renderCellValue(
                    Array.isArray(row.scopes) ? row.scopes.join(', ') : row.scopes,
                  )}
                </td>
                <td>{renderCellValue(row.autoApprove ? '是' : '否')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SocialClientWorkspace() {
  const clientQuery = useQuery({
    queryKey: ['module-special', 'social-client', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/social-client/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = clientQuery.data?.list || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">认证体系</div>
          <h2>社交客户端</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => clientQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新社交配置
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">客户端数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">平台种类</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.socialType || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">用户类型</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.userType || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/social-client/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`social-client-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.clientId)} · {renderCellValue(row.agentId)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">平台</div>
            <div className="text-sm">{renderCellValue(row.socialType)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.userType)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">社交</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>平台</th>
              <th>用户类型</th>
              <th>Client ID</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`social-client-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.socialType)}</td>
                <td>{renderCellValue(row.userType)}</td>
                <td>{renderCellValue(row.clientId)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SocialUserWorkspace() {
  const userQuery = useQuery({
    queryKey: ['module-special', 'social-user', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/social-user/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const bindListQuery = useQuery({
    queryKey: ['module-special', 'social-user', 'bind-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/social-user/get-bind-list'),
  });
  const rows = userQuery.data?.list || [];
  const bindRows = bindListQuery.data || [];

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">认证体系</div>
          <h2>社交用户</h2>
        </div>
        <button
          className="subtle-chip"
          type="button"
          onClick={() => {
            userQuery.refetch();
            bindListQuery.refetch();
          }}
        >
          <ArrowsClockwise size={14} />
          刷新社交用户
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">绑定数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">当前用户绑定</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{bindRows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">平台类型</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.type || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/social-user/page
          </div>
        </div>
      </div>

      <div className="border-b border-[var(--line)] px-5 py-4">
        <div className="mb-3 text-sm font-medium">当前登录用户绑定关系</div>
        {bindRows.length > 0 ? (
          <div className="grid gap-2 md:grid-cols-2">
            {bindRows.map((row, index) => (
              <div
                key={`social-bind-self-${index}`}
                className="border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm"
              >
                <div className="font-medium text-[var(--text)]">
                  {renderCellValue(row.nickname)}
                </div>
                <div className="mt-1 text-[var(--text-muted)]">
                  平台：{renderCellValue(row.type)}
                </div>
                <div className="mt-1 text-[var(--text-muted)]">
                  OpenID：{renderCellValue(row.openid)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-[var(--text-muted)]">
            当前登录用户没有已绑定的社交账号。
          </div>
        )}
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`social-user-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.nickname)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.openid)} · {renderCellValue(row.type)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">平台类型</div>
            <div className="text-sm">{renderCellValue(row.type)}</div>
            <div className="text-sm">{renderCellValue(row.code)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">绑定</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>昵称</th>
              <th>平台类型</th>
              <th>OpenID</th>
              <th>授权码</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`social-user-table-${index}`}>
                <td>{renderCellValue(row.nickname)}</td>
                <td>{renderCellValue(row.type)}</td>
                <td>{renderCellValue(row.openid)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FileWorkspace() {
  const [uploadMode, setUploadMode] = useState<'backend' | 'presigned'>('backend');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [directory, setDirectory] = useState('');
  const [actionError, setActionError] = useState('');
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const fileQuery = useQuery({
    queryKey: ['module-special', 'infra-file', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/file/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = fileQuery.data?.list || [];
  const totalSize = rows.reduce((sum, row) => sum + Number(row.size || 0), 0);

  const backendUploadMutation = useMutation({
    mutationFn: async () => {
      if (!uploadFile) {
        throw new Error('请选择要上传的文件');
      }
      return http.upload<string>('/infra/file/upload', {
        directory: directory || undefined,
        file: uploadFile,
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '后端上传失败');
      setUploadResult(null);
    },
    onSuccess: async (path) => {
      setActionError('');
      setUploadResult({ path, type: 'backend-upload' });
      await fileQuery.refetch();
    },
  });

  const presignedUploadMutation = useMutation({
    mutationFn: async () => {
      if (!uploadFile) {
        throw new Error('请选择要上传的文件');
      }
      const presigned = await http.get<{
        configId: number;
        path: string;
        uploadUrl: string;
        url: string;
      }>('/infra/file/presigned-url', {
        params: {
          directory: directory || undefined,
          name: uploadFile.name,
        },
      });
      const uploadResponse = await fetch(presigned.uploadUrl, {
        body: uploadFile,
        method: 'PUT',
        headers: {
          'Content-Type': uploadFile.type || 'application/octet-stream',
        },
      });
      if (!uploadResponse.ok) {
        throw new Error(`预签名上传失败：${uploadResponse.status}`);
      }
      const recordId = await http.post<number>('/infra/file/create', {
        configId: presigned.configId,
        name: uploadFile.name,
        path: presigned.path,
        size: uploadFile.size,
        type: uploadFile.type,
        url: presigned.url,
      });
      return { ...presigned, recordId };
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '预签名上传失败');
      setUploadResult(null);
    },
    onSuccess: async (result) => {
      setActionError('');
      setUploadResult(result);
      await fileQuery.refetch();
    },
  });

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.9fr)]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">文件中心</div>
            <h2>文件存储</h2>
          </div>
          <button className="subtle-chip" type="button" onClick={() => fileQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新文件
          </button>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">文件数量</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">累计大小</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{totalSize}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">配置来源</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {new Set(rows.map((row) => String(row.configId || '')).filter(Boolean)).size}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">接口来源</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">/infra/file/page</div>
          </div>
        </div>

        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="shell-subtitle text-pretty">
            同时承接后端直传和预签名直传两条真实文件链路，上传完成后立即回写文件台账。
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="subtle-chip">/infra/file/upload</span>
            <span className="subtle-chip">/infra/file/presigned-url</span>
            <span className="subtle-chip">/infra/file/create</span>
          </div>
        </div>

        <div className="work-list border-b border-[var(--line)]">
          {rows.slice(0, 6).map((row, index) => (
            <div key={`file-row-${index}`} className="work-row">
              <div>
                <div className="text-sm font-medium text-[var(--text)]">
                  {renderCellValue(row.name || row.path)}
                </div>
                <div className="mt-1 work-meta">
                  {renderCellValue(row.path)} · {renderCellValue(row.type)}
                </div>
              </div>
              <div className="text-sm text-[var(--text-muted)]">配置</div>
              <div className="text-sm">{renderCellValue(row.configId)}</div>
              <div className="text-sm">{renderCellValue(row.size)}</div>
              <div className="text-sm text-[var(--text-muted)]">
                {renderCellValue(row.createTime)}
              </div>
              <div className="text-right text-xs text-[var(--text-soft)]">文件</div>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="dense-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>路径</th>
                <th>类型</th>
                <th>大小</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`file-table-${index}`}>
                  <td>{renderCellValue(row.name || row.path)}</td>
                  <td>{renderCellValue(row.path)}</td>
                  <td>{renderCellValue(row.type)}</td>
                  <td>{renderCellValue(row.size)}</td>
                  <td>{renderCellValue(row.createTime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">上传处理台</div>
            <h2>{uploadMode === 'backend' ? '后端直传' : '预签名直传'}</h2>
          </div>
          <div className="flex items-center gap-2">
            {[
              { key: 'backend', label: '后端直传' },
              { key: 'presigned', label: '预签名直传' },
            ].map((item) => (
              <button
                key={item.key}
                className={
                  uploadMode === item.key
                    ? 'subtle-chip bg-white text-[var(--text)]'
                    : 'subtle-chip'
                }
                type="button"
                onClick={() => setUploadMode(item.key as 'backend' | 'presigned')}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {actionError ? (
          <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 text-sm font-medium">上传参数</div>
          <div className="grid gap-3">
            <label className="flex items-center gap-3 border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
              <span className="text-[var(--text-muted)]">目标目录</span>
              <input
                className="w-full bg-transparent outline-none"
                placeholder="例如 approval/attachments"
                value={directory}
                onChange={(event) => setDirectory(event.target.value)}
              />
            </label>
            <label className="flex items-center gap-3 border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
              <span className="text-[var(--text-muted)]">选择文件</span>
              <input
                type="file"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              />
            </label>
            <button
              className="subtle-chip w-fit"
              disabled={backendUploadMutation.isPending || presignedUploadMutation.isPending}
              type="button"
              onClick={() => {
                setActionError('');
                if (uploadMode === 'backend') {
                  backendUploadMutation.mutate();
                  return;
                }
                presignedUploadMutation.mutate();
              }}
            >
              {backendUploadMutation.isPending || presignedUploadMutation.isPending
                ? '上传中...'
                : uploadMode === 'backend'
                  ? '执行后端直传'
                  : '执行预签名直传'}
            </button>
          </div>
        </div>

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 text-sm font-medium">当前结果</div>
          <div className="grid gap-2 text-sm text-[var(--text-muted)]">
            <div>文件：{uploadFile?.name || '-'}</div>
            <div>模式：{uploadMode === 'backend' ? '后端直传' : '预签名直传'}</div>
            <div>目录：{directory || '-'}</div>
            <div>结果路径：{renderCellValue(uploadResult?.path)}</div>
            <div>访问地址：{renderCellValue(uploadResult?.url)}</div>
          </div>
        </div>

        <div className="px-5 py-4">
          <div className="mb-2 text-sm font-medium">链路说明</div>
          <div className="grid gap-2 text-xs text-[var(--text-muted)]">
            <div>模式一：文件直接发到 `/infra/file/upload`，由后端落库并返回路径。</div>
            <div>模式二：先调 `/infra/file/presigned-url`，再 PUT 到对象存储，最后调 `/infra/file/create` 记台账。</div>
          </div>
        </div>
      </aside>
    </div>
  );
}

function FileConfigWorkspace() {
  const configQuery = useQuery({
    queryKey: ['module-special', 'infra-file-config', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/file-config/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = configQuery.data?.list || [];
  const visibleRows = countTruthyValues(rows, 'visible');
  const masterRows = countTruthyValues(rows, 'master');

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">文件中心</div>
          <h2>文件配置</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => configQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新配置
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">配置数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">主配置</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{masterRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">可见配置</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{visibleRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /infra/file-config/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`file-config-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.storage)} · {renderCellValue(row.remark)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">域名</div>
            <div className="text-sm">
              {renderCellValue(
                typeof row.config === 'object' && row.config
                  ? (row.config as Record<string, unknown>).domain
                  : '-',
              )}
            </div>
            <div className="text-sm">{renderCellValue(row.master ? '主配置' : '备份')}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.visible ? '可见' : '隐藏')}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">配置</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>存储器</th>
              <th>主配置</th>
              <th>可见</th>
              <th>域名</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`file-config-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.storage)}</td>
                <td>{renderCellValue(row.master ? '是' : '否')}</td>
                <td>{renderCellValue(row.visible ? '是' : '否')}</td>
                <td>
                  {renderCellValue(
                    typeof row.config === 'object' && row.config
                      ? (row.config as Record<string, unknown>).domain
                      : '-',
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AreaWorkspace() {
  const areaQuery = useQuery({
    queryKey: ['module-special', 'system-area', 'tree'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/area/tree'),
  });
  const treeRows = areaQuery.data || [];
  const rows = flattenTreeRows(treeRows);

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">基础字典</div>
          <h2>地区管理</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => areaQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新地区
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">树根节点</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {treeRows.length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">地区总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">最深层级</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {rows.reduce((max, row) => Math.max(max, Number(row.__level || 0)), 0)}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/area/tree</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 8).map((row, index) => (
          <div key={`area-row-${index}`} className="work-row">
            <div>
              <div
                className="text-sm font-medium text-[var(--text)]"
                style={{ paddingLeft: `${Number(row.__level || 0) * 16}px` }}
              >
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">{renderCellValue(row.code)}</div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">父级</div>
            <div className="text-sm">{renderCellValue(row.parentId)}</div>
            <div className="text-sm">{renderCellValue(row.sort)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.status)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">地区</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>地区名称</th>
              <th>编码</th>
              <th>父级</th>
              <th>排序</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`area-table-${index}`}>
                <td style={{ paddingLeft: `${12 + Number(row.__level || 0) * 16}px` }}>
                  {renderCellValue(row.name)}
                </td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.parentId)}</td>
                <td>{renderCellValue(row.sort)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function NoticeWorkspace() {
  const noticeQuery = useQuery({
    queryKey: ['module-special', 'system-notice', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/notice/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = noticeQuery.data?.list || [];
  const publishedRows = rows.filter((row) => Number(row.status) === 1).length;

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">系统公告</div>
          <h2>公告发布</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => noticeQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新公告
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">公告总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">已发布</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {publishedRows}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">公告类型</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.type || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/notice/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`notice-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.title)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.creator)} · {renderCellValue(row.createTime)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">类型</div>
            <div className="text-sm">{renderCellValue(row.type)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.remark)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">公告</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>标题</th>
              <th>类型</th>
              <th>状态</th>
              <th>创建人</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`notice-table-${index}`}>
                <td>{renderCellValue(row.title)}</td>
                <td>{renderCellValue(row.type)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.creator)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LoginLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'system-login-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/login-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const successRows = rows.filter((row) => Number(row.result) === 0).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/login-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-login-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">审计轨迹</div>
          <h2>登录日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新登录日志
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">日志数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">成功登录</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{successRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">来源 IP</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.userIp || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/login-log/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`login-log-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.username)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.userIp)} · {renderCellValue(row.userAgent)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">用户类型</div>
            <div className="text-sm">{renderCellValue(row.userType)}</div>
            <div className="text-sm">{renderCellValue(row.result)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">登录</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>结果</th>
              <th>IP</th>
              <th>User Agent</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`login-log-table-${index}`}>
                <td>{renderCellValue(row.username)}</td>
                <td>{renderCellValue(row.result)}</td>
                <td>{renderCellValue(row.userIp)}</td>
                <td>{renderCellValue(row.userAgent)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OperateLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'system-operate-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/operate-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/operate-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-operate-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">审计轨迹</div>
          <h2>操作日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新操作日志
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">日志数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">操作模块</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.type || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">操作人</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.userName || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/operate-log/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`operate-log-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.action)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.userName)} · {renderCellValue(row.requestMethod)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">业务类型</div>
            <div className="text-sm">
              {renderCellValue(row.type)} / {renderCellValue(row.subType)}
            </div>
            <div className="text-sm">{renderCellValue(row.requestUrl)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">审计</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>操作人</th>
              <th>动作</th>
              <th>类型</th>
              <th>请求地址</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`operate-log-table-${index}`}>
                <td>{renderCellValue(row.userName)}</td>
                <td>{renderCellValue(row.action)}</td>
                <td>{renderCellValue(row.type)}</td>
                <td>{renderCellValue(row.requestUrl)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ApiAccessLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'infra-api-access-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/api-access-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/infra/api-access-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'infra-api-access-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">接口治理</div>
          <h2>API 访问日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新访问日志
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">日志数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">平均耗时</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {rows.length
              ? Math.round(
                  rows.reduce((sum, row) => sum + Number(row.duration || 0), 0) /
                    rows.length,
                )
              : 0}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">结果码种类</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.resultCode || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /infra/api-access-log/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`api-access-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.requestMethod)} {renderCellValue(row.requestUrl)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.operateModule)} · {renderCellValue(row.operateName)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">调用来源</div>
            <div className="text-sm">{renderCellValue(row.applicationName)}</div>
            <div className="text-sm">{renderCellValue(row.duration)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.resultCode)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">访问</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>方法</th>
              <th>地址</th>
              <th>模块</th>
              <th>耗时</th>
              <th>结果码</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`api-access-table-${index}`}>
                <td>{renderCellValue(row.requestMethod)}</td>
                <td>{renderCellValue(row.requestUrl)}</td>
                <td>{renderCellValue(row.operateModule)}</td>
                <td>{renderCellValue(row.duration)}</td>
                <td>{renderCellValue(row.resultCode)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ApiErrorLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'infra-api-error-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/api-error-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const processedRows = rows.filter((row) => Number(row.processStatus) === 1).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/infra/api-error-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'infra-api-error-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">接口治理</div>
          <h2>API 错误日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新错误日志
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">错误数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">已处理</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {processedRows}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">异常类种类</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.exceptionName || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /infra/api-error-log/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`api-error-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.exceptionName)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.requestMethod)} · {renderCellValue(row.requestUrl)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">根因</div>
            <div className="text-sm">
              {renderCellValue(row.exceptionRootCauseMessage || row.exceptionMessage)}
            </div>
            <div className="text-sm">{renderCellValue(row.processStatus)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.exceptionTime || row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">异常</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>异常类</th>
              <th>请求地址</th>
              <th>结果码</th>
              <th>处理状态</th>
              <th>异常时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`api-error-table-${index}`}>
                <td>{renderCellValue(row.exceptionName)}</td>
                <td>{renderCellValue(row.requestUrl)}</td>
                <td>{renderCellValue(row.resultCode)}</td>
                <td>{renderCellValue(row.processStatus)}</td>
                <td>{renderCellValue(row.exceptionTime || row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TenantWorkspace() {
  const tenantQuery = useQuery({
    queryKey: ['module-special', 'system-tenant', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/tenant/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = tenantQuery.data?.list || [];
  const activeRows = rows.filter((row) => Number(row.status) === 0).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/tenant/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-tenant.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">多租户体系</div>
          <h2>租户管理</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出租户'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => tenantQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新租户
          </button>
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">租户数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用租户</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{activeRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">套餐种类</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.packageId || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/tenant/page</div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`tenant-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.contactName)} · {renderCellValue(row.contactMobile)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">套餐</div>
            <div className="text-sm">{renderCellValue(row.packageId)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.expireTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">租户</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>租户名</th>
              <th>联系人</th>
              <th>手机号</th>
              <th>状态</th>
              <th>到期时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`tenant-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.contactName)}</td>
                <td>{renderCellValue(row.contactMobile)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.expireTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TenantPackageWorkspace() {
  const packageQuery = useQuery({
    queryKey: ['module-special', 'system-tenant-package', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/tenant-package/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = packageQuery.data?.list || [];
  const enabledRows = rows.filter((row) => Number(row.status) === 0).length;

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">多租户体系</div>
          <h2>租户套餐</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => packageQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新套餐
        </button>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">套餐数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">启用套餐</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{enabledRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">菜单配置</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {rows.reduce(
              (sum, row) =>
                sum +
                (Array.isArray(row.menuIds) ? row.menuIds.length : 0),
              0,
            )}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            /system/tenant-package/page
          </div>
        </div>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`tenant-package-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.name)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.creator)} · {renderCellValue(row.updater)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">菜单数量</div>
            <div className="text-sm">
              {renderCellValue(Array.isArray(row.menuIds) ? row.menuIds.length : 0)}
            </div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.updateTime || row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">套餐</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>套餐名称</th>
              <th>状态</th>
              <th>创建人</th>
              <th>更新人</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`tenant-package-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.creator)}</td>
                <td>{renderCellValue(row.updater)}</td>
                <td>{renderCellValue(row.updateTime || row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function UserWorkspace() {
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [updateSupport, setUpdateSupport] = useState(false);
  const [actionError, setActionError] = useState('');
  const userQuery = useQuery({
    queryKey: ['module-special', 'system-user', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/user/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const roleOptionsQuery = useQuery({
    queryKey: ['module-special', 'system-role', 'simple-list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/role/simple-list'),
  });
  const userRoleQuery = useQuery({
    queryKey: ['module-special', 'system-user', 'role-list', selectedUserId],
    queryFn: () =>
      http.get<number[]>('/system/permission/list-user-roles', {
        params: { userId: selectedUserId },
      }),
    enabled: selectedUserId !== null,
  });
  const rows = userQuery.data?.list || [];
  const activeRows = rows.filter((row) => Number(row.status) === 0).length;
  const selectedUser =
    rows.find((row) => Number(row.id) === selectedUserId) || rows[0] || null;
  const roleOptions = roleOptionsQuery.data || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/user/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-user.xlsx'),
  });

  useEffect(() => {
    if (!selectedUserId && rows[0]?.id) {
      setSelectedUserId(Number(rows[0].id));
    }
  }, [rows, selectedUserId]);

  useEffect(() => {
    if (userRoleQuery.data) {
      setSelectedRoleIds(userRoleQuery.data.map((item) => Number(item)));
    }
  }, [userRoleQuery.data]);

  const assignRoleMutation = useMutation({
    mutationFn: async () => {
      if (!selectedUserId) {
        throw new Error('请选择需要分配角色的用户');
      }
      return http.post<boolean>('/system/permission/assign-user-role', {
        roleIds: selectedRoleIds,
        userId: selectedUserId,
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '分配角色失败');
    },
    onSuccess: async () => {
      setActionError('');
      await userRoleQuery.refetch();
    },
  });

  const importTemplateMutation = useMutation({
    mutationFn: async () => http.download('/system/user/get-import-template'),
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '下载导入模板失败');
    },
    onSuccess: (blob) => {
      setActionError('');
      downloadBlobFile(blob, 'system-user-import-template.xls');
    },
  });

  const importUserMutation = useMutation({
    mutationFn: async () => {
      if (!importFile) {
        throw new Error('请选择要导入的 Excel 文件');
      }
      return http.upload<Record<string, unknown>>('/system/user/import', {
        file: importFile,
        updateSupport: String(updateSupport),
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '导入用户失败');
    },
    onSuccess: async () => {
      setActionError('');
      setImportFile(null);
      await userQuery.refetch();
    },
  });

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.9fr)]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">组织与权限</div>
            <h2>用户管理</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="subtle-chip"
              disabled={exportMutation.isPending}
              type="button"
              onClick={() => exportMutation.mutate()}
            >
              {exportMutation.isPending ? '导出中...' : '导出用户'}
            </button>
            <button className="subtle-chip" type="button" onClick={() => userQuery.refetch()}>
              <ArrowsClockwise size={14} />
              刷新用户
            </button>
          </div>
        </div>
        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">用户数量</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">启用用户</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{activeRows}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">部门覆盖</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {new Set(rows.map((row) => String(row.deptId || '')).filter(Boolean)).size}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">接口来源</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">/system/user/page</div>
          </div>
        </div>
        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="shell-subtitle text-pretty">
            把用户浏览、角色分配和 Excel 导入收进同一处理面，避免在多层弹窗里来回切换。
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="subtle-chip">/system/permission/list-user-roles</span>
            <span className="subtle-chip">/system/permission/assign-user-role</span>
            <span className="subtle-chip">/system/user/get-import-template</span>
            <span className="subtle-chip">/system/user/import</span>
          </div>
        </div>
        <div className="work-list border-b border-[var(--line)]">
          {rows.slice(0, 8).map((row, index) => {
            const rowId = Number(row.id || 0);
            const active = rowId === selectedUserId;
            return (
              <button
                key={`user-row-${index}`}
                className={active ? 'work-row bg-[#f7fafc] text-left' : 'work-row text-left'}
                type="button"
                onClick={() => {
                  setActionError('');
                  setSelectedUserId(rowId);
                }}
              >
                <div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {renderCellValue(row.nickname)}
                  </div>
                  <div className="mt-1 work-meta">
                    {renderCellValue(row.username)} · {renderCellValue(row.mobile)}
                  </div>
                </div>
                <div className="text-sm text-[var(--text-muted)]">部门</div>
                <div className="text-sm">{renderCellValue(row.deptId)}</div>
                <div className="text-sm">{renderCellValue(row.status)}</div>
                <div className="text-sm text-[var(--text-muted)]">
                  {renderCellValue(row.loginIp)}
                </div>
                <div className="text-right text-xs text-[var(--text-soft)]">
                  {active ? '当前处理' : '用户'}
                </div>
              </button>
            );
          })}
        </div>
        <div className="overflow-x-auto">
          <table className="dense-table">
            <thead>
              <tr>
                <th>姓名</th>
                <th>用户名</th>
                <th>手机号</th>
                <th>邮箱</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`user-table-${index}`}>
                  <td>{renderCellValue(row.nickname)}</td>
                  <td>{renderCellValue(row.username)}</td>
                  <td>{renderCellValue(row.mobile)}</td>
                  <td>{renderCellValue(row.email)}</td>
                  <td>{renderCellValue(row.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">当前处理台</div>
            <h2>{renderCellValue(selectedUser?.nickname || '请选择用户')}</h2>
          </div>
          <button
            className="subtle-chip"
            disabled={assignRoleMutation.isPending || !selectedUserId}
            type="button"
            onClick={() => assignRoleMutation.mutate()}
          >
            {assignRoleMutation.isPending ? '提交中...' : '保存角色分配'}
          </button>
        </div>

        {actionError ? (
          <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-2">
          <div className="detail-block">
            <div className="work-meta">用户名</div>
            <div className="mt-2 text-sm font-medium">{renderCellValue(selectedUser?.username)}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">部门 ID</div>
            <div className="mt-2 text-sm font-medium">{renderCellValue(selectedUser?.deptId)}</div>
          </div>
        </div>

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 text-sm font-medium">用户角色分配</div>
          <div className="grid gap-2">
            {roleOptions.map((role) => {
              const roleId = Number(role.id || 0);
              const checked = selectedRoleIds.includes(roleId);
              return (
                <label
                  key={roleId}
                  className="flex items-center justify-between border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm"
                >
                  <span>
                    {renderCellValue(role.name)} · {renderCellValue(role.code)}
                  </span>
                  <input
                    checked={checked}
                    type="checkbox"
                    onChange={(event) => {
                      setSelectedRoleIds((current) =>
                        event.target.checked
                          ? [...current, roleId]
                          : current.filter((item) => item !== roleId),
                      );
                    }}
                  />
                </label>
              );
            })}
          </div>
        </div>

        <div className="px-5 py-4">
          <div className="mb-3 text-sm font-medium">用户导入</div>
          <div className="grid gap-3">
            <button
              className="subtle-chip w-fit"
              disabled={importTemplateMutation.isPending}
              type="button"
              onClick={() => importTemplateMutation.mutate()}
            >
              {importTemplateMutation.isPending ? '下载中...' : '下载导入模板'}
            </button>
            <label className="flex items-center gap-3 border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm">
              <span className="text-[var(--text-muted)]">选择 Excel</span>
              <input
                type="file"
                accept=".xls,.xlsx"
                onChange={(event) => setImportFile(event.target.files?.[0] || null)}
              />
            </label>
            <label className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <input
                checked={updateSupport}
                type="checkbox"
                onChange={(event) => setUpdateSupport(event.target.checked)}
              />
              是否允许按用户名更新已存在用户
            </label>
            <button
              className="subtle-chip w-fit"
              disabled={importUserMutation.isPending}
              type="button"
              onClick={() => importUserMutation.mutate()}
            >
              {importUserMutation.isPending ? '导入中...' : '执行用户导入'}
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function RoleWorkspace() {
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [selectedMenuIds, setSelectedMenuIds] = useState<number[]>([]);
  const [selectedDeptIds, setSelectedDeptIds] = useState<number[]>([]);
  const [dataScope, setDataScope] = useState<number>(1);
  const [actionError, setActionError] = useState('');
  const roleQuery = useQuery({
    queryKey: ['module-special', 'system-role', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/role/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const menuQuery = useQuery({
    queryKey: ['module-special', 'system-menu', 'list-all'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/menu/list'),
  });
  const deptQuery = useQuery({
    queryKey: ['module-special', 'system-dept', 'list-all'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/dept/list'),
  });
  const roleDetailQuery = useQuery({
    queryKey: ['module-special', 'system-role', 'get', selectedRoleId],
    queryFn: () =>
      http.get<Record<string, unknown>>('/system/role/get', {
        params: { id: selectedRoleId },
      }),
    enabled: selectedRoleId !== null,
  });
  const roleMenuQuery = useQuery({
    queryKey: ['module-special', 'system-role', 'menu-list', selectedRoleId],
    queryFn: () =>
      http.get<number[]>('/system/permission/list-role-menus', {
        params: { roleId: selectedRoleId },
      }),
    enabled: selectedRoleId !== null,
  });
  const rows = roleQuery.data?.list || [];
  const selectedRole =
    rows.find((row) => Number(row.id) === selectedRoleId) || rows[0] || null;
  const flatMenuRows = flattenTreeRows(menuQuery.data || []);
  const flatDeptRows = flattenTreeRows(deptQuery.data || []);
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/role/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-role.xlsx'),
  });

  useEffect(() => {
    if (!selectedRoleId && rows[0]?.id) {
      setSelectedRoleId(Number(rows[0].id));
    }
  }, [rows, selectedRoleId]);

  useEffect(() => {
    const detail = roleDetailQuery.data;
    if (!detail) {
      return;
    }
    setDataScope(Number(detail.dataScope || 1));
    setSelectedDeptIds(
      Array.isArray(detail.dataScopeDeptIds)
        ? (detail.dataScopeDeptIds as unknown[]).map((item) => Number(item))
        : [],
    );
  }, [roleDetailQuery.data]);

  useEffect(() => {
    if (roleMenuQuery.data) {
      setSelectedMenuIds(roleMenuQuery.data.map((item) => Number(item)));
    }
  }, [roleMenuQuery.data]);

  const assignMenuMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRoleId) {
        throw new Error('请选择角色');
      }
      return http.post<boolean>('/system/permission/assign-role-menu', {
        menuIds: selectedMenuIds,
        roleId: selectedRoleId,
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '菜单权限保存失败');
    },
    onSuccess: async () => {
      setActionError('');
      await roleMenuQuery.refetch();
    },
  });

  const assignDataScopeMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRoleId) {
        throw new Error('请选择角色');
      }
      return http.post<boolean>('/system/permission/assign-role-data-scope', {
        dataScope,
        dataScopeDeptIds: dataScope === 2 ? selectedDeptIds : [],
        roleId: selectedRoleId,
      });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : '数据权限保存失败');
    },
    onSuccess: async () => {
      setActionError('');
      await roleDetailQuery.refetch();
    },
  });

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.9fr)]">
      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">组织与权限</div>
            <h2>角色管理</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="subtle-chip"
              disabled={exportMutation.isPending}
              type="button"
              onClick={() => exportMutation.mutate()}
            >
              {exportMutation.isPending ? '导出中...' : '导出角色'}
            </button>
            <button className="subtle-chip" type="button" onClick={() => roleQuery.refetch()}>
              <ArrowsClockwise size={14} />
              刷新角色
            </button>
          </div>
        </div>
        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">角色数量</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">角色类型</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {new Set(rows.map((row) => String(row.type || '')).filter(Boolean)).size}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">数据范围</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {new Set(rows.map((row) => String(row.dataScope || '')).filter(Boolean)).size}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">接口来源</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">/system/role/page</div>
          </div>
        </div>
        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="shell-subtitle text-pretty">
            当前角色页承接菜单权限和数据权限两类分配动作，按角色选中后直接在右侧处理，不走独立弹窗流。
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="subtle-chip">/system/permission/list-role-menus</span>
            <span className="subtle-chip">/system/permission/assign-role-menu</span>
            <span className="subtle-chip">/system/permission/assign-role-data-scope</span>
          </div>
        </div>
        <div className="work-list border-b border-[var(--line)]">
          {rows.slice(0, 8).map((row, index) => {
            const rowId = Number(row.id || 0);
            const active = rowId === selectedRoleId;
            return (
              <button
                key={`role-row-${index}`}
                className={active ? 'work-row bg-[#f7fafc] text-left' : 'work-row text-left'}
                type="button"
                onClick={() => {
                  setActionError('');
                  setSelectedRoleId(rowId);
                }}
              >
                <div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {renderCellValue(row.name)}
                  </div>
                  <div className="mt-1 work-meta">
                    {renderCellValue(row.code)} · {renderCellValue(row.sort)}
                  </div>
                </div>
                <div className="text-sm text-[var(--text-muted)]">类型</div>
                <div className="text-sm">{renderCellValue(row.type)}</div>
                <div className="text-sm">{renderCellValue(row.dataScope)}</div>
                <div className="text-sm text-[var(--text-muted)]">
                  {renderCellValue(row.status)}
                </div>
                <div className="text-right text-xs text-[var(--text-soft)]">
                  {active ? '当前处理' : '角色'}
                </div>
              </button>
            );
          })}
        </div>
        <div className="overflow-x-auto">
          <table className="dense-table">
            <thead>
              <tr>
                <th>角色名</th>
                <th>编码</th>
                <th>类型</th>
                <th>数据范围</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`role-table-${index}`}>
                  <td>{renderCellValue(row.name)}</td>
                  <td>{renderCellValue(row.code)}</td>
                  <td>{renderCellValue(row.type)}</td>
                  <td>{renderCellValue(row.dataScope)}</td>
                  <td>{renderCellValue(row.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">当前处理台</div>
            <h2>{renderCellValue(selectedRole?.name || '请选择角色')}</h2>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="subtle-chip"
              disabled={assignMenuMutation.isPending || !selectedRoleId}
              type="button"
              onClick={() => assignMenuMutation.mutate()}
            >
              {assignMenuMutation.isPending ? '提交中...' : '保存菜单权限'}
            </button>
            <button
              className="subtle-chip"
              disabled={assignDataScopeMutation.isPending || !selectedRoleId}
              type="button"
              onClick={() => assignDataScopeMutation.mutate()}
            >
              {assignDataScopeMutation.isPending ? '提交中...' : '保存数据范围'}
            </button>
          </div>
        </div>

        {actionError ? (
          <div className="border-b border-[var(--line)] bg-[#fff6f4] px-5 py-3 text-sm text-[var(--danger)]">
            {actionError}
          </div>
        ) : null}

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-2">
          <div className="detail-block">
            <div className="work-meta">角色编码</div>
            <div className="mt-2 text-sm font-medium">{renderCellValue(selectedRole?.code)}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">当前数据范围</div>
            <div className="mt-2 text-sm font-medium">{renderCellValue(dataScope)}</div>
          </div>
        </div>

        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="mb-3 text-sm font-medium">数据权限范围</div>
          <div className="grid gap-2">
            {[
              { label: '全部数据', value: 1 },
              { label: '指定部门', value: 2 },
              { label: '本部门', value: 3 },
              { label: '本部门及子部门', value: 4 },
              { label: '仅本人', value: 5 },
            ].map((item) => (
              <label
                key={item.value}
                className="flex items-center justify-between border border-[var(--line)] bg-[var(--panel)] px-3 py-3 text-sm"
              >
                <span>{item.label}</span>
                <input
                  checked={dataScope === item.value}
                  type="radio"
                  name="data-scope"
                  onChange={() => setDataScope(item.value)}
                />
              </label>
            ))}
          </div>
        </div>

        {dataScope === 2 ? (
          <div className="border-b border-[var(--line)] px-5 py-4">
            <div className="mb-3 text-sm font-medium">指定部门范围</div>
            <div className="max-h-[220px] overflow-auto border border-[var(--line)]">
              {flatDeptRows.map((dept, index) => {
                const deptId = Number(dept.id || 0);
                const checked = selectedDeptIds.includes(deptId);
                return (
                  <label
                    key={`dept-permission-${index}`}
                    className="flex items-center justify-between border-b border-[var(--line)] bg-white px-3 py-3 text-sm last:border-b-0"
                    style={{ paddingLeft: `${12 + Number(dept.__level || 0) * 16}px` }}
                  >
                    <span>{renderCellValue(dept.name)}</span>
                    <input
                      checked={checked}
                      type="checkbox"
                      onChange={(event) => {
                        setSelectedDeptIds((current) =>
                          event.target.checked
                            ? [...current, deptId]
                            : current.filter((item) => item !== deptId),
                        );
                      }}
                    />
                  </label>
                );
              })}
            </div>
          </div>
        ) : null}

        <div className="px-5 py-4">
          <div className="mb-3 text-sm font-medium">菜单权限分配</div>
          <div className="max-h-[280px] overflow-auto border border-[var(--line)]">
            {flatMenuRows.map((menu, index) => {
              const menuId = Number(menu.id || 0);
              const checked = selectedMenuIds.includes(menuId);
              return (
                <label
                  key={`menu-permission-${index}`}
                  className="flex items-center justify-between border-b border-[var(--line)] bg-white px-3 py-3 text-sm last:border-b-0"
                  style={{ paddingLeft: `${12 + Number(menu.__level || 0) * 16}px` }}
                >
                  <span>
                    {renderCellValue(menu.name)}
                    {menu.permission ? ` · ${renderCellValue(menu.permission)}` : ''}
                  </span>
                  <input
                    checked={checked}
                    type="checkbox"
                    onChange={(event) => {
                      setSelectedMenuIds((current) =>
                        event.target.checked
                          ? [...current, menuId]
                          : current.filter((item) => item !== menuId),
                      );
                    }}
                  />
                </label>
              );
            })}
          </div>
        </div>
      </aside>
    </div>
  );
}

function DeptWorkspace() {
  const deptQuery = useQuery({
    queryKey: ['module-special', 'system-dept', 'list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/dept/list'),
  });
  const treeRows = deptQuery.data || [];
  const rows = flattenTreeRows(treeRows);
  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">组织与权限</div>
          <h2>部门管理</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => deptQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新部门
        </button>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">根部门</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{treeRows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">部门总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">负责人覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {countTruthyValues(rows, 'leaderUserId')}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/dept/list</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>部门名称</th>
              <th>父级</th>
              <th>负责人</th>
              <th>电话</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`dept-table-${index}`}>
                <td style={{ paddingLeft: `${12 + Number(row.__level || 0) * 16}px` }}>
                  {renderCellValue(row.name)}
                </td>
                <td>{renderCellValue(row.parentId)}</td>
                <td>{renderCellValue(row.leaderUserId)}</td>
                <td>{renderCellValue(row.phone)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MenuWorkspace() {
  const menuQuery = useQuery({
    queryKey: ['module-special', 'system-menu', 'list'],
    queryFn: () => http.get<Record<string, unknown>[]>('/system/menu/list'),
  });
  const treeRows = menuQuery.data || [];
  const rows = flattenTreeRows(treeRows);
  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">组织与权限</div>
          <h2>菜单管理</h2>
        </div>
        <button className="subtle-chip" type="button" onClick={() => menuQuery.refetch()}>
          <ArrowsClockwise size={14} />
          刷新菜单
        </button>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">菜单总数</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">权限点</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {countTruthyValues(rows, 'permission')}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">可见菜单</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {countTruthyValues(rows, 'visible')}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/menu/list</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>路径</th>
              <th>权限标识</th>
              <th>类型</th>
              <th>可见</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`menu-table-${index}`}>
                <td style={{ paddingLeft: `${12 + Number(row.__level || 0) * 16}px` }}>
                  {renderCellValue(row.name)}
                </td>
                <td>{renderCellValue(row.path)}</td>
                <td>{renderCellValue(row.permission)}</td>
                <td>{renderCellValue(row.type)}</td>
                <td>{renderCellValue(row.visible ? '是' : '否')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PostWorkspace() {
  const postQuery = useQuery({
    queryKey: ['module-special', 'system-post', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/post/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = postQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/post/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-post.xlsx'),
  });
  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">组织与权限</div>
          <h2>岗位管理</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出岗位'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => postQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新岗位
          </button>
        </div>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">岗位数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">岗位编码</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {countTruthyValues(rows, 'code')}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">状态覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.status || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/post/page</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>岗位名称</th>
              <th>编码</th>
              <th>排序</th>
              <th>状态</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`post-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.code)}</td>
                <td>{renderCellValue(row.sort)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DictTypeWorkspace() {
  const typeQuery = useQuery({
    queryKey: ['module-special', 'system-dict-type', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/dict-type/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = typeQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/dict-type/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-dict-type.xlsx'),
  });
  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">基础字典</div>
          <h2>字典类型</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出类型'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => typeQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新字典类型
          </button>
        </div>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">类型数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">标识数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {countTruthyValues(rows, 'type')}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">状态覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.status || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/dict-type/page</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>字典类型</th>
              <th>状态</th>
              <th>备注</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`dict-type-table-${index}`}>
                <td>{renderCellValue(row.name)}</td>
                <td>{renderCellValue(row.type)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.remark)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DictDataWorkspace() {
  const dataQuery = useQuery({
    queryKey: ['module-special', 'system-dict-data', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/dict-data/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = dataQuery.data?.list || [];
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/dict-data/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-dict-data.xlsx'),
  });
  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">基础字典</div>
          <h2>字典数据</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出数据'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => dataQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新字典数据
          </button>
        </div>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">数据数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">字典类型</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.dictType || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">颜色类型</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.colorType || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/dict-data/page</div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>标签</th>
              <th>值</th>
              <th>字典类型</th>
              <th>颜色类型</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`dict-data-table-${index}`}>
                <td>{renderCellValue(row.label)}</td>
                <td>{renderCellValue(row.value)}</td>
                <td>{renderCellValue(row.dictType)}</td>
                <td>{renderCellValue(row.colorType)}</td>
                <td>{renderCellValue(row.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SmsLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'system-sms-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/system/sms-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const successRows = rows.filter((row) => Number(row.sendStatus) === 10).length;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/system/sms-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'system-sms-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">通知系统</div>
          <h2>短信日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新日志
          </button>
        </div>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">发送记录</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">发送成功</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{successRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">模板覆盖</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {new Set(rows.map((row) => String(row.templateCode || ''))).size}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/system/sms-log/page</div>
        </div>
      </div>
      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`sms-log-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.mobile)}
              </div>
              <div className="mt-1 work-meta">
                {renderCellValue(row.templateCode)} · {renderCellValue(row.channelCode)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">发送状态</div>
            <div className="text-sm">{renderCellValue(row.sendStatus)}</div>
            <div className="text-sm">{renderCellValue(row.apiSendCode || row.serialNo)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.createTime)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">短信</div>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>手机号</th>
              <th>模板编码</th>
              <th>渠道</th>
              <th>发送状态</th>
              <th>发送时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`sms-log-table-${index}`}>
                <td>{renderCellValue(row.mobile)}</td>
                <td>{renderCellValue(row.templateCode)}</td>
                <td>{renderCellValue(row.channelCode)}</td>
                <td>{renderCellValue(row.sendStatus)}</td>
                <td>{renderCellValue(row.createTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function JobLogWorkspace() {
  const logQuery = useQuery({
    queryKey: ['module-special', 'infra-job-log', 'page'],
    queryFn: () =>
      http.get<PageResult<Record<string, unknown>>>('/infra/job-log/page', {
        params: { pageNo: 1, pageSize: 20 },
      }),
  });
  const rows = logQuery.data?.list || [];
  const successRows = rows.filter((row) => Number(row.status) === 0).length;
  const avgDuration = rows.length
    ? Math.round(
        rows.reduce((sum, row) => sum + Number(row.duration || 0), 0) / rows.length,
      )
    : 0;
  const exportMutation = useMutation({
    mutationFn: () => http.download('/infra/job-log/export-excel'),
    onSuccess: (blob) => downloadBlobFile(blob, 'infra-job-log.xlsx'),
  });

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">运维监管</div>
          <h2>任务日志</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="subtle-chip"
            disabled={exportMutation.isPending}
            type="button"
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? '导出中...' : '导出日志'}
          </button>
          <button className="subtle-chip" type="button" onClick={() => logQuery.refetch()}>
            <ArrowsClockwise size={14} />
            刷新任务日志
          </button>
        </div>
      </div>
      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">日志数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{rows.length}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">执行成功</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{successRows}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">平均耗时</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">{avgDuration}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">/infra/job-log/page</div>
        </div>
      </div>
      <div className="work-list border-b border-[var(--line)]">
        {rows.slice(0, 6).map((row, index) => (
          <div key={`job-log-row-${index}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderCellValue(row.handlerName)}
              </div>
              <div className="mt-1 work-meta">
                任务 {renderCellValue(row.jobId)} · {renderCellValue(row.handlerParam)}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">开始时间</div>
            <div className="text-sm">{renderCellValue(row.beginTime)}</div>
            <div className="text-sm">{renderCellValue(row.status)}</div>
            <div className="text-sm text-[var(--text-muted)]">
              {renderCellValue(row.duration)}
            </div>
            <div className="text-right text-xs text-[var(--text-soft)]">调度</div>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              <th>任务 ID</th>
              <th>处理器</th>
              <th>参数</th>
              <th>状态</th>
              <th>耗时</th>
              <th>开始时间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`job-log-table-${index}`}>
                <td>{renderCellValue(row.jobId)}</td>
                <td>{renderCellValue(row.handlerName)}</td>
                <td>{renderCellValue(row.handlerParam)}</td>
                <td>{renderCellValue(row.status)}</td>
                <td>{renderCellValue(row.duration)}</td>
                <td>{renderCellValue(row.beginTime)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ModulePage() {
  const { moduleKey = '' } = useParams();
  const [keyword, setKeyword] = useState('');
  const module = moduleRegistry.find((item) => item.key === moduleKey);

  const listQuery = useQuery({
    enabled: Boolean(module),
    queryKey: ['module-page', moduleKey],
    queryFn: () => queryModuleList(module!),
  });

  const sectionModules = useMemo(() => {
    if (!module) {
      return [];
    }
    return moduleRegistry.filter((item) => item.section === module.section);
  }, [module]);

  if (!module) {
    return (
      <section className="surface px-6 py-8">
        <div className="hairline-title">模块不存在</div>
        <div className="mt-2 text-lg font-semibold">未找到对应后端模块映射</div>
      </section>
    );
  }

  const currentSection = navSections.find((item) => item.key === module.section);
  if (module.key === 'system-notify-message') {
    return <NotifyMessageWorkspace />;
  }
  if (module.key === 'infra-job') {
    return <JobWorkspace />;
  }
  if (module.key === 'infra-codegen') {
    return <CodegenWorkspace />;
  }
  if (module.key === 'infra-redis') {
    return <RedisWorkspace />;
  }
  if (module.key === 'system-mail-template') {
    return <MailTemplateWorkspace />;
  }
  if (module.key === 'system-mail-account') {
    return <MailAccountWorkspace />;
  }
  if (module.key === 'system-user') {
    return <UserWorkspace />;
  }
  if (module.key === 'system-role') {
    return <RoleWorkspace />;
  }
  if (module.key === 'system-dept') {
    return <DeptWorkspace />;
  }
  if (module.key === 'system-menu') {
    return <MenuWorkspace />;
  }
  if (module.key === 'system-post') {
    return <PostWorkspace />;
  }
  if (module.key === 'system-dict-type') {
    return <DictTypeWorkspace />;
  }
  if (module.key === 'system-dict-data') {
    return <DictDataWorkspace />;
  }
  if (module.key === 'system-notify-template') {
    return <NotifyTemplateWorkspace />;
  }
  if (module.key === 'system-mail-log') {
    return <MailLogWorkspace />;
  }
  if (module.key === 'system-social-client') {
    return <SocialClientWorkspace />;
  }
  if (module.key === 'system-notice') {
    return <NoticeWorkspace />;
  }
  if (module.key === 'system-social-user') {
    return <SocialUserWorkspace />;
  }
  if (module.key === 'system-sms-channel') {
    return <SmsChannelWorkspace />;
  }
  if (module.key === 'system-sms-template') {
    return <SmsTemplateWorkspace />;
  }
  if (module.key === 'system-sms-log') {
    return <SmsLogWorkspace />;
  }
  if (module.key === 'system-login-log') {
    return <LoginLogWorkspace />;
  }
  if (module.key === 'system-operate-log') {
    return <OperateLogWorkspace />;
  }
  if (module.key === 'system-oauth2-client') {
    return <OAuth2ClientWorkspace />;
  }
  if (module.key === 'system-oauth2-token') {
    return <OAuth2TokenWorkspace />;
  }
  if (module.key === 'system-area') {
    return <AreaWorkspace />;
  }
  if (module.key === 'system-tenant') {
    return <TenantWorkspace />;
  }
  if (module.key === 'system-tenant-package') {
    return <TenantPackageWorkspace />;
  }
  if (module.key === 'infra-config') {
    return <ConfigWorkspace />;
  }
  if (module.key === 'infra-data-source-config') {
    return <DataSourceWorkspace />;
  }
  if (module.key === 'infra-file') {
    return <FileWorkspace />;
  }
  if (module.key === 'infra-file-config') {
    return <FileConfigWorkspace />;
  }
  if (module.key === 'infra-job-log') {
    return <JobLogWorkspace />;
  }
  if (module.key === 'infra-api-access-log') {
    return <ApiAccessLogWorkspace />;
  }
  if (module.key === 'infra-api-error-log') {
    return <ApiErrorLogWorkspace />;
  }
  const rows = listQuery.data?.list || [];
  const columns =
    module.columns && module.columns.length > 0
      ? module.columns
      : Object.keys(rows[0] || {}).slice(0, 6).map((key) => ({ key, label: key }));
  const filteredRows = rows.filter((row) => {
    if (!keyword.trim()) {
      return true;
    }
    const text = JSON.stringify(row).toLowerCase();
    return text.includes(keyword.trim().toLowerCase());
  });
  const firstColumn = columns[0]?.key;
  const secondColumn = columns[1]?.key;
  const thirdColumn = columns[2]?.key;
  const statusColumn = columns.find((item) => /status/i.test(item.key))?.key;
  const timeColumn = columns.find((item) => /time/i.test(item.key))?.key;
  const primaryValueKey = firstColumn || '';
  const secondaryValueKey = secondColumn || '';
  const tertiaryValueKey = thirdColumn || '';

  return (
    <div className="grid gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">{currentSection?.label || '模块域'}</div>
            <h2>{currentSection?.label || '系统模块'}</h2>
          </div>
        </div>
        <div className="px-5 py-4">
          <div className="shell-subtitle text-pretty">
            {currentSection?.subtitle || '统一承接组织、消息、租户和基础设施模块'}
          </div>
        </div>
        <div className="border-t border-[var(--line)] px-3 py-3">
          <div className="space-y-1">
            {sectionModules.map((item) => (
              <Link
                key={item.key}
                className={
                  item.key === module.key
                    ? 'block border border-[var(--line)] bg-[var(--panel-muted)] px-3 py-3'
                    : 'block border border-transparent px-3 py-3 hover:bg-[var(--panel-muted)]'
                }
                to={item.path}
              >
                <div className="text-sm font-medium text-[var(--text)]">{item.label}</div>
                <div className="mt-1 text-xs text-[var(--text-soft)]">{item.description}</div>
              </Link>
            ))}
          </div>
        </div>
      </aside>

      <section className="surface overflow-hidden">
        <div className="section-heading">
          <div>
            <div className="hairline-title">{currentSection?.label || '模块页面'}</div>
            <h2>{module.label}</h2>
          </div>
          <div className="shell-subtitle max-w-[420px] text-right text-pretty">
            {module.description}
          </div>
        </div>

        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-[1.2fr_0.8fr_0.8fr_0.8fr]">
          <div className="detail-block">
            <div className="work-meta">接口来源</div>
            <div className="mt-2 text-sm font-medium">{module.listPath || '未配置'}</div>
          </div>
          <div className="detail-block">
            <div className="work-meta">当前记录</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {filteredRows.length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">带状态字段</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {countTruthyValues(filteredRows, statusColumn)}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">最近时间字段</div>
            <div className="mt-2 text-sm font-medium">
              {timeColumn && filteredRows[0]?.[timeColumn]
                ? renderCellValue(filteredRows[0][timeColumn])
                : '-'}
            </div>
          </div>
        </div>

        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
            <label className="flex items-center gap-3 border border-[var(--line)] bg-white px-3 py-3 text-sm">
              <MagnifyingGlass size={16} className="text-[var(--text-soft)]" />
              <input
                className="w-full bg-transparent outline-none"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder={`按 ${columns[0]?.label || '关键字'}、${columns[1]?.label || '字段'} 搜索`}
              />
            </label>
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <span className="subtle-chip">{module.listMode === 'page' ? '分页接口' : '列表接口'}</span>
              <span className="subtle-chip">{columns.length} 个重点字段</span>
              <span className="subtle-chip">{filteredRows.length} 条结果</span>
            </div>
          </div>
          <button
            aria-label="刷新模块数据"
            className="subtle-chip"
            type="button"
            onClick={() => listQuery.refetch()}
          >
            <ArrowsClockwise size={14} />
            刷新数据
          </button>
        </div>

        <div className="work-list border-b border-[var(--line)]">
          {filteredRows.slice(0, 6).map((row, index) => (
            <div key={`${module.key}-digest-${index}`} className="work-row">
              <div>
                <div className="text-sm font-medium text-[var(--text)]">
                  {renderCellValue(primaryValueKey ? row[primaryValueKey] : '-')}
                </div>
                <div className="mt-1 work-meta">
                  {columns[1]?.label || secondaryValueKey}：
                  {renderCellValue(secondaryValueKey ? row[secondaryValueKey] : '-')}
                </div>
              </div>
              <div className="text-sm text-[var(--text-muted)]">
                {columns[2]?.label || tertiaryValueKey}
              </div>
              <div className="text-sm">
                {renderCellValue(tertiaryValueKey ? row[tertiaryValueKey] : '-')}
              </div>
              <div className="text-sm">{renderCellValue(statusColumn ? row[statusColumn] : '-')}</div>
              <div className="text-sm text-[var(--text-muted)]">
                {renderCellValue(timeColumn ? row[timeColumn] : '-')}
              </div>
              <div className="text-right text-xs text-[var(--text-soft)]">
                #{index + 1}
              </div>
            </div>
          ))}
          {filteredRows.length === 0 ? (
            <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
              当前没有可展示的数据，或筛选条件没有命中结果。
            </div>
          ) : null}
        </div>

        <div className="overflow-x-auto">
          <table className="dense-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row, index) => (
                <tr key={`${module.key}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.key}>{renderCellValue(row[column.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
