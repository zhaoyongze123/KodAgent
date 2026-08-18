import { http, type PageParams, type PageResult } from '@/shared/api/http';

export type AssetType =
  | 'categories'
  | 'definitions'
  | 'expressions'
  | 'forms'
  | 'groups'
  | 'listeners'
  | 'models';

const assetPathMap: Record<AssetType, string> = {
  categories: '/bpm/category/page',
  definitions: '/bpm/process-definition/page',
  expressions: '/bpm/process-expression/page',
  forms: '/bpm/form/page',
  groups: '/bpm/user-group/page',
  listeners: '/bpm/process-listener/page',
  models: '/bpm/model/list',
};

export async function getAssetList(assetType: AssetType, params: PageParams) {
  const path = assetPathMap[assetType];
  if (assetType === 'models') {
    const list = await http.get<Record<string, unknown>[]>(path, { params });
    return { list, total: list.length } as PageResult<Record<string, unknown>>;
  }
  return http.get<PageResult<Record<string, unknown>>>(path, { params });
}
