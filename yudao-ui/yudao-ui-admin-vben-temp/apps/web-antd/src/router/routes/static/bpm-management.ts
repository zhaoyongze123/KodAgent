import type { RouteRecordRaw } from 'vue-router';

const BasicLayout = () => import('#/layouts/basic.vue');

const routes: RouteRecordRaw[] = [
  {
    path: '/bpm',
    component: BasicLayout,
    meta: {
      hideInMenu: true,
      title: '工作流',
    },
    children: [
      {
        path: 'category',
        name: 'BpmCategoryStatic',
        component: () => import('#/views/bpm/category/index.vue'),
        meta: {
          title: '流程分类',
          activePath: '/bpm/category',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'group',
        name: 'BpmGroupStatic',
        component: () => import('#/views/bpm/group/index.vue'),
        meta: {
          title: '用户组',
          activePath: '/bpm/group',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-expression',
        name: 'BpmProcessExpressionStatic',
        component: () => import('#/views/bpm/processExpression/index.vue'),
        meta: {
          title: '流程表达式',
          activePath: '/bpm/process-expression',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/template',
        name: 'BpmApprovalTemplateStatic',
        component: () => import('#/views/bpm/approvalTemplate/index.vue'),
        meta: {
          title: '审批模板管理',
          activePath: '/bpm/manager/template',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-instance/manager',
        name: 'BpmProcessInstanceManagerStatic',
        component: () => import('#/views/bpm/processInstance/manager/index.vue'),
        meta: {
          title: '流程实例',
          activePath: '/bpm/process-instance/manager',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-listener',
        name: 'BpmProcessListenerStatic',
        component: () => import('#/views/bpm/processListener/index.vue'),
        meta: {
          title: '流程监听器',
          activePath: '/bpm/process-listener',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
