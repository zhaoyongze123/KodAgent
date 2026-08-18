import { useQuery } from '@tanstack/react-query';
import { ArrowsClockwise, MagnifyingGlass } from '@phosphor-icons/react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getAssetList, type AssetType } from '@/entities/asset/api/asset-api';
import { formatDateTime } from '@/shared/lib/format';

const assetMetaMap: Record<
  AssetType,
  { description: string; subtitle: string; title: string }
> = {
  categories: {
    description: '维护审批分类与展示顺序，保证发起入口和流程归档一致。',
    subtitle: '分类、编码、排序与状态',
    title: '流程分类',
  },
  definitions: {
    description: '查看已部署流程的版本、状态、表单绑定和发起入口。',
    subtitle: '部署流程与发起配置',
    title: '流程定义',
  },
  expressions: {
    description: '管理流程中用到的动态表达式与规则逻辑。',
    subtitle: '动态审批规则库',
    title: '流程表达式',
  },
  forms: {
    description: '统一查看动态表单与字段结构，支撑审批发起和详情展示。',
    subtitle: '表单结构与绑定',
    title: '流程表单',
  },
  groups: {
    description: '审批候选组管理，面向部门组、角色组和固定审批群体。',
    subtitle: '候选人分组与成员',
    title: '用户组',
  },
  listeners: {
    description: '管理流程监听器，覆盖回调、状态同步和外部触发能力。',
    subtitle: '流程事件监听',
    title: '流程监听器',
  },
  models: {
    description: '流程模型是定义审批结构的核心资产，决定后续部署版本。',
    subtitle: '流程设计源',
    title: '流程模型',
  },
};

const assetTabs: AssetType[] = [
  'models',
  'definitions',
  'forms',
  'categories',
  'groups',
  'expressions',
  'listeners',
];

function renderAssetCell(value: unknown) {
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

export function AssetManagementPage() {
  const { assetType = 'models' } = useParams();
  const [keyword, setKeyword] = useState('');
  const currentType = assetType as AssetType;
  const currentMeta = assetMetaMap[currentType] || assetMetaMap.models;

  const assetQuery = useQuery({
    queryKey: ['asset-list', currentType],
    queryFn: () => getAssetList(currentType, { pageNo: 1, pageSize: 20 }),
  });

  const rows = assetQuery.data?.list || [];
  const headers = Object.keys(rows[0] || {}).slice(0, 8);
  const filteredRows = useMemo(() => {
    if (!keyword.trim()) {
      return rows;
    }
    return rows.filter((row) =>
      JSON.stringify(row).toLowerCase().includes(keyword.trim().toLowerCase()),
    );
  }, [keyword, rows]);

  return (
    <section className="surface overflow-hidden">
      <div className="section-heading">
        <div>
          <div className="hairline-title">流程资产</div>
          <h2>{currentMeta.title}</h2>
        </div>
        <div className="shell-subtitle max-w-[420px] text-right text-pretty">
          {currentMeta.description}
        </div>
      </div>

      <div className="border-b border-[var(--line)] px-5 py-4">
        <div className="mb-2 text-sm font-medium">{currentMeta.subtitle}</div>
        <div className="flex flex-wrap gap-2">
          {assetTabs.map((item) => (
            <Link
              key={item}
              className={
                item === currentType
                  ? 'subtle-chip border-[var(--line-strong)] bg-white text-[var(--text)]'
                  : 'subtle-chip bg-[var(--panel-muted)] text-[var(--text-muted)]'
              }
              to={`/assets/${item}`}
            >
              {assetMetaMap[item].title}
            </Link>
          ))}
        </div>
      </div>

      <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
        <div className="detail-block">
          <div className="work-meta">当前资产</div>
          <div className="mt-2 text-lg font-semibold">{currentMeta.title}</div>
        </div>
        <div className="detail-block">
          <div className="work-meta">当前条目</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {filteredRows.length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">字段数量</div>
          <div className="mt-2 text-[24px] font-semibold tabular-nums">
            {headers.length}
          </div>
        </div>
        <div className="detail-block">
          <div className="work-meta">接口来源</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            {currentType === 'models'
              ? '/bpm/model/list'
              : `/bpm/${currentType.replace('-', '/')}/page`}
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
            placeholder={`按 ${headers[0] || '关键字段'} 搜索资产`}
          />
        </label>
        <div className="subtle-chip justify-center">
          先筛资产，再进入部署、表单或规则维护
        </div>
        <button
          aria-label="刷新资产数据"
          className="subtle-chip"
          type="button"
          onClick={() => assetQuery.refetch()}
        >
          <ArrowsClockwise size={14} />
          刷新
        </button>
      </div>

      <div className="work-list border-b border-[var(--line)]">
        {filteredRows.slice(0, 6).map((row, rowIndex) => (
          <div key={`${currentType}-digest-${rowIndex}`} className="work-row">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">
                {renderAssetCell(row[headers[0] || ''])}
              </div>
              <div className="mt-1 work-meta">
                {headers[1] || '字段二'}：{renderAssetCell(row[headers[1] || ''])}
              </div>
            </div>
            <div className="text-sm text-[var(--text-muted)]">{headers[2] || '字段三'}</div>
            <div className="text-sm">{renderAssetCell(row[headers[2] || ''])}</div>
            <div className="text-sm text-[var(--text-muted)]">{headers[3] || '字段四'}</div>
            <div className="text-sm">{renderAssetCell(row[headers[3] || ''])}</div>
            <div className="text-right text-xs text-[var(--text-soft)]">
              #{rowIndex + 1}
            </div>
          </div>
        ))}
        {filteredRows.length === 0 ? (
          <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
            当前没有资产数据，或搜索条件没有命中结果。
          </div>
        ) : null}
      </div>

      <div className="overflow-x-auto">
        <table className="dense-table">
          <thead>
            <tr>
              {headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row, rowIndex) => (
              <tr key={`${currentType}-${rowIndex}`}>
                {headers.map((header) => (
                  <td key={header}>{renderAssetCell(row[header])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
