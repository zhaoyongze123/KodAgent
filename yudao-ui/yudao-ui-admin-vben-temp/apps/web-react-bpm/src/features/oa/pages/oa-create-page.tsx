import { useParams } from 'react-router-dom';

import { OACreateForm } from '@/features/oa/components/oa-create-form';
import { oaModuleConfigs } from '@/features/oa/config/oa-module-config';

export function OACreatePage() {
  const { moduleKey = '' } = useParams();

  if (!(moduleKey in oaModuleConfigs)) {
    return (
      <section className="surface px-6 py-8">
        <div className="hairline-title">未找到流程</div>
        <div className="mt-2 text-lg font-semibold">该 OA 模块尚未映射到 React 工作台</div>
      </section>
    );
  }

  return <OACreateForm moduleKey={moduleKey as keyof typeof oaModuleConfigs} />;
}
