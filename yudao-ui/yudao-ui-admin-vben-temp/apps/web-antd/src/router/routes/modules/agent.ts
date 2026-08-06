import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/agent/model',
    component: () => import('#/views/agent/model/index.vue'),
    name: 'AgentModel',
    meta: {
      title: 'Agent 模型管理',
      icon: 'ant-design:robot-filled',
      authority: ['system:agent-model:query'],
    },
  },
];

export default routes;
