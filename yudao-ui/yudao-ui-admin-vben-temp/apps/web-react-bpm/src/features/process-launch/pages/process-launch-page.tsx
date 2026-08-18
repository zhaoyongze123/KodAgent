import { useMemo, useState, type ChangeEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MagnifyingGlass } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';

import { getCategorySimpleList } from '@/entities/category/api/category-api';
import {
  getProcessDefinitionList,
  type ProcessDefinition,
} from '@/entities/process-definition/api/process-definition-api';
import { oaModuleConfigs, oaModuleOrder } from '@/features/oa/config/oa-module-config';

export function ProcessLaunchPage() {
  const [searchValue, setSearchValue] = useState('');
  const categoryQuery = useQuery({
    queryKey: ['launch-categories'],
    queryFn: getCategorySimpleList,
  });
  const definitionQuery = useQuery({
    queryKey: ['launch-definitions'],
    queryFn: () => getProcessDefinitionList(),
  });

  const groupedDefinitions = useMemo(() => {
    const map = new Map<string, ProcessDefinition[]>();
    (definitionQuery.data || []).forEach((item) => {
      const categoryName = item.categoryName || item.category || '未分类';
      const list = map.get(categoryName) || [];
      if (!searchValue || item.name.includes(searchValue)) {
        list.push(item);
      }
      map.set(categoryName, list);
    });
    return Array.from(map.entries()).filter(([, list]) => list.length > 0);
  }, [definitionQuery.data, searchValue]);

  return (
    <div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="surface px-4 py-4">
        <div className="hairline-title">流程分类</div>
        <div className="mt-4 space-y-2">
          {(categoryQuery.data || []).map((item) => (
            <div key={item.id} className="border-b border-[var(--line)] pb-2 text-sm">
              {item.name}
            </div>
          ))}
        </div>
      </aside>

      <section className="surface">
        <div className="section-heading">
          <div>
            <div className="hairline-title">发起审批</div>
            <h2>流程目录</h2>
          </div>
          <div className="shell-subtitle max-w-[420px] text-right text-pretty">
            先从 OA 业务申请进入高频场景，再按流程定义目录发起标准流程。
          </div>
        </div>
        <div className="grid gap-0 border-b border-[var(--line)] lg:grid-cols-4">
          <div className="detail-block">
            <div className="work-meta">流程分类</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {(categoryQuery.data || []).length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">流程定义</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {(definitionQuery.data || []).length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">OA 表单</div>
            <div className="mt-2 text-[24px] font-semibold tabular-nums">
              {oaModuleOrder.length}
            </div>
          </div>
          <div className="detail-block">
            <div className="work-meta">处理节奏</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">
              先选业务入口，再进入具体发起表单
            </div>
          </div>
        </div>
        <div className="grid gap-4 border-b border-[var(--line)] px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto]">
          <label className="flex items-center gap-3 border border-[var(--line)] bg-white px-3 py-3 text-sm">
            <MagnifyingGlass size={16} className="text-[var(--text-soft)]" />
            <input
              className="w-full bg-transparent outline-none"
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setSearchValue(event.target.value)
              }
              placeholder="搜索流程名称"
              value={searchValue}
            />
          </label>
          <button
            className="subtle-chip justify-center"
            type="button"
            onClick={() => {
              categoryQuery.refetch();
              definitionQuery.refetch();
            }}
          >
            刷新目录
          </button>
        </div>
        <div className="border-b border-[var(--line)] px-5 py-5">
          <div className="mb-3 text-sm font-semibold">OA 业务申请</div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {oaModuleOrder.map((key) => {
              const item = oaModuleConfigs[key];
              return (
                <Link
                  key={item.key}
                  className="border border-[var(--line)] bg-[var(--panel-muted)] px-4 py-3"
                  to={`/launch/oa/${item.key}`}
                >
                  <div className="font-medium">{item.title}</div>
                  <div className="mt-1 text-sm text-[var(--text-muted)]">
                    {item.description}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {groupedDefinitions.map(([categoryName, items]) => (
            <div key={categoryName} className="px-5 py-5">
              <div className="mb-3 text-sm font-semibold">{categoryName}</div>
              <div className="space-y-2">
                {items.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[minmax(0,1fr)_120px] items-center gap-4 border border-transparent border-b-[var(--line)] py-3"
                  >
                    <div>
                      <div className="font-medium">{item.name}</div>
                      <div className="mt-1 text-sm text-[var(--text-muted)]">
                        {item.description || '暂无流程说明'}
                      </div>
                    </div>
                    <button className="border border-[var(--line)] bg-white px-3 py-2 text-sm font-medium">
                      发起
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {groupedDefinitions.length === 0 ? (
            <div className="px-5 py-8 text-sm text-[var(--text-muted)]">
              当前没有命中的流程定义。
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
