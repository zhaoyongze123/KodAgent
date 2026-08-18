import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/bpm',
    name: 'bpm',
    meta: {
      title: '工作流',
      hideInMenu: true,
    },
    children: [
      {
        path: 'process-instance/detail',
        component: () => import('#/views/bpm/processInstance/detail/index.vue'),
        name: 'BpmProcessInstanceDetail',
        meta: {
          title: '流程详情',
          activePath: '/bpm/task/my',
          icon: 'ant-design:history-outlined',
          keepAlive: false,
          hideInMenu: true,
        },
        props: (route) => {
          return {
            id: route.query.id,
            taskId: route.query.taskId,
            activityId: route.query.activityId,
          };
        },
      },
      {
        path: 'category',
        component: () => import('#/views/bpm/category/index.vue'),
        name: 'BpmCategory',
        meta: {
          title: '流程分类',
          activePath: '/bpm/category',
          icon: 'carbon:categories',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/form',
        component: () => import('#/views/bpm/form/index.vue'),
        name: 'BpmForm',
        meta: {
          title: '流程表单',
          activePath: '/bpm/manager/form',
          icon: 'carbon:document',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/template',
        component: () => import('#/views/bpm/approvalTemplate/index.vue'),
        name: 'BpmApprovalTemplate',
        meta: {
          title: '审批模板管理',
          activePath: '/bpm/manager/template',
          icon: 'carbon:template',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: '/bpm/manager/form/edit',
        name: 'BpmFormEditor',
        component: () => import('#/views/bpm/form/designer/index.vue'),
        meta: {
          title: '设计流程表单',
          activePath: '/bpm/manager/form',
        },
        props: (route) => {
          return {
            id: route.query.id,
            type: route.query.type,
            copyId: route.query.copyId,
          };
        },
      },
      {
        path: 'manager/model',
        component: () => import('#/views/bpm/model/index.vue'),
        name: 'BpmModel',
        meta: {
          title: '流程模型',
          activePath: '/bpm/manager/model',
          icon: 'carbon:flow',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/model/create',
        component: () => import('#/views/bpm/model/form/index.vue'),
        name: 'BpmModelCreate',
        meta: {
          title: '创建流程',
          activePath: '/bpm/manager/model',
          icon: 'carbon:flow-connection',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/model/:type/:id',
        component: () => import('#/views/bpm/model/form/index.vue'),
        name: 'BpmModelUpdate',
        meta: {
          title: '修改流程',
          activePath: '/bpm/manager/model',
          icon: 'carbon:flow-connection',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'manager/definition',
        component: () => import('#/views/bpm/model/definition/index.vue'),
        name: 'BpmProcessDefinition',
        meta: {
          title: '流程定义',
          activePath: '/bpm/manager/definition',
          icon: 'carbon:flow-modeler',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-instance/manager',
        component: () => import('#/views/bpm/processInstance/manager/index.vue'),
        name: 'BpmProcessInstanceManager',
        meta: {
          title: '流程实例',
          activePath: '/bpm/process-instance/manager',
          icon: 'carbon:document-signed',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'group',
        component: () => import('#/views/bpm/group/index.vue'),
        name: 'BpmGroup',
        meta: {
          title: '用户组',
          activePath: '/bpm/group',
          icon: 'carbon:user-multiple',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-expression',
        component: () => import('#/views/bpm/processExpression/index.vue'),
        name: 'BpmProcessExpression',
        meta: {
          title: '流程表达式',
          activePath: '/bpm/process-expression',
          icon: 'carbon:function-math',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-listener',
        component: () => import('#/views/bpm/processListener/index.vue'),
        name: 'BpmProcessListener',
        meta: {
          title: '流程监听器',
          activePath: '/bpm/process-listener',
          icon: 'carbon:notification',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'process-instance/report',
        component: () => import('#/views/bpm/processInstance/report/index.vue'),
        name: 'BpmProcessInstanceReport',
        meta: {
          title: '数据报表',
          activePath: '/bpm/manager/model',
          icon: 'carbon:data-2',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
