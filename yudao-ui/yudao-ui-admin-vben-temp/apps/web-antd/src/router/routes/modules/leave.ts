import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/bpm/oa',
    name: 'OALeave',
    meta: {
      title: 'OA请假',
      hideInMenu: true,
      redirect: '/bpm/oa/leave/index',
    },
    children: [
      {
        path: 'leave',
        name: 'OALeaveIndex',
        component: () => import('#/views/bpm/oa/leave/index.vue'),
        meta: {
          title: '请假列表',
          activePath: '/bpm/oa/leave',
        },
      },
      {
        path: 'leave/create',
        name: 'OALeaveCreate',
        component: () => import('#/views/bpm/oa/leave/create.vue'),
        meta: {
          title: '创建请假',
          activePath: '/bpm/oa/leave',
        },
      },
      {
        path: 'leave/detail',
        name: 'OALeaveDetail',
        component: () => import('#/views/bpm/oa/leave/detail.vue'),
        meta: {
          title: '请假详情',
          activePath: '/bpm/oa/leave',
        },
      },
      {
        path: 'trip',
        name: 'OATripIndex',
        component: () => import('#/views/bpm/oa/trip/index.vue'),
        meta: {
          title: '出差列表',
          activePath: '/bpm/oa/trip',
        },
      },
      {
        path: 'trip/create',
        name: 'OATripCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'trip' },
        meta: {
          title: '创建出差',
          activePath: '/bpm/oa/trip',
        },
      },
      {
        path: 'trip/detail',
        name: 'OATripDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'trip',
          id: route.query.id,
        }),
        meta: {
          title: '出差详情',
          activePath: '/bpm/oa/trip',
        },
      },
      {
        path: 'outing',
        name: 'OAOutingIndex',
        component: () => import('#/views/bpm/oa/outing/index.vue'),
        meta: {
          title: '临时外出列表',
          activePath: '/bpm/oa/outing',
        },
      },
      {
        path: 'outing/create',
        name: 'OAOutingCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'outing' },
        meta: {
          title: '创建临时外出',
          activePath: '/bpm/oa/outing',
        },
      },
      {
        path: 'outing/detail',
        name: 'OAOutingDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'outing',
          id: route.query.id,
        }),
        meta: {
          title: '临时外出详情',
          activePath: '/bpm/oa/outing',
        },
      },
      {
        path: 'overtime',
        name: 'OAOvertimeIndex',
        component: () => import('#/views/bpm/oa/overtime/index.vue'),
        meta: {
          title: '加班列表',
          activePath: '/bpm/oa/overtime',
        },
      },
      {
        path: 'overtime/create',
        name: 'OAOvertimeCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'overtime' },
        meta: {
          title: '创建加班',
          activePath: '/bpm/oa/overtime',
        },
      },
      {
        path: 'overtime/detail',
        name: 'OAOvertimeDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'overtime',
          id: route.query.id,
        }),
        meta: {
          title: '加班详情',
          activePath: '/bpm/oa/overtime',
        },
      },
      {
        path: 'leave-cancel',
        name: 'OALeaveCancelIndex',
        component: () => import('#/views/bpm/oa/leave-cancel/index.vue'),
        meta: {
          title: '销假列表',
          activePath: '/bpm/oa/leave-cancel',
        },
      },
      {
        path: 'leave-cancel/create',
        name: 'OALeaveCancelCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'leaveCancel' },
        meta: {
          title: '创建销假',
          activePath: '/bpm/oa/leave-cancel',
        },
      },
      {
        path: 'leave-cancel/detail',
        name: 'OALeaveCancelDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'leaveCancel',
          id: route.query.id,
        }),
        meta: {
          title: '销假详情',
          activePath: '/bpm/oa/leave-cancel',
        },
      },
      {
        path: 'attendance',
        name: 'OAAttendanceIndex',
        component: () => import('#/views/bpm/oa/attendance/index.vue'),
        meta: {
          title: '补卡列表',
          activePath: '/bpm/oa/attendance',
        },
      },
      {
        path: 'attendance/create',
        name: 'OAAttendanceCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'attendance' },
        meta: {
          title: '创建补卡',
          activePath: '/bpm/oa/attendance',
        },
      },
      {
        path: 'attendance/detail',
        name: 'OAAttendanceDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'attendance',
          id: route.query.id,
        }),
        meta: {
          title: '补卡详情',
          activePath: '/bpm/oa/attendance',
        },
      },
      {
        path: 'expense',
        name: 'OAExpenseIndex',
        component: () => import('#/views/bpm/oa/expense/index.vue'),
        meta: {
          title: '报销列表',
          activePath: '/bpm/oa/expense',
        },
      },
      {
        path: 'expense/create',
        name: 'OAExpenseCreate',
        component: () => import('#/views/bpm/oa/shared/create-page.vue'),
        props: { moduleKey: 'expense' },
        meta: {
          title: '创建报销',
          activePath: '/bpm/oa/expense',
        },
      },
      {
        path: 'expense/detail',
        name: 'OAExpenseDetail',
        component: () => import('#/views/bpm/oa/shared/detail-page.vue'),
        props: (route) => ({
          moduleKey: 'expense',
          id: route.query.id,
        }),
        meta: {
          title: '报销详情',
          activePath: '/bpm/oa/expense',
        },
      },
      {
        path: 'seal',
        name: 'OASealIndex',
        component: () => import('#/views/bpm/oa/seal/index.vue'),
        meta: {
          title: '用章列表',
          activePath: '/bpm/oa/seal',
        },
      },
      {
        path: 'seal/create',
        name: 'OASealCreate',
        component: () => import('#/views/bpm/oa/seal/create.vue'),
        meta: {
          title: '创建用章',
          activePath: '/bpm/oa/seal',
        },
      },
      {
        path: 'seal/detail',
        name: 'OASealDetail',
        component: () => import('#/views/bpm/oa/seal/detail.vue'),
        meta: {
          title: '用章详情',
          activePath: '/bpm/oa/seal',
        },
      },
      {
        path: 'document',
        name: 'OADocumentIndex',
        component: () => import('#/views/bpm/oa/document/index.vue'),
        meta: {
          title: '合同/文件审批列表',
          activePath: '/bpm/oa/document',
        },
      },
      {
        path: 'document/create',
        name: 'OADocumentCreate',
        component: () => import('#/views/bpm/oa/document/create.vue'),
        meta: {
          title: '创建合同/文件审批',
          activePath: '/bpm/oa/document',
        },
      },
      {
        path: 'document/detail',
        name: 'OADocumentDetail',
        component: () => import('#/views/bpm/oa/document/detail.vue'),
        meta: {
          title: '合同/文件审批详情',
          activePath: '/bpm/oa/document',
        },
      },
      {
        path: 'project',
        name: 'OAProjectIndex',
        component: () => import('#/views/bpm/oa/project/index.vue'),
        meta: {
          title: '项目立项申请列表',
          activePath: '/bpm/oa/project',
        },
      },
      {
        path: 'project/create',
        name: 'OAProjectCreate',
        component: () => import('#/views/bpm/oa/project/create.vue'),
        meta: {
          title: '创建项目立项申请',
          activePath: '/bpm/oa/project',
        },
      },
      {
        path: 'project/detail',
        name: 'OAProjectDetail',
        component: () => import('#/views/bpm/oa/project/detail.vue'),
        meta: {
          title: '项目立项申请详情',
          activePath: '/bpm/oa/project',
        },
      },
      {
        path: 'staffing',
        name: 'OAStaffingIndex',
        component: () => import('#/views/bpm/oa/staffing/index.vue'),
        meta: {
          title: '项目人员调配申请列表',
          activePath: '/bpm/oa/staffing',
        },
      },
      {
        path: 'staffing/create',
        name: 'OAStaffingCreate',
        component: () => import('#/views/bpm/oa/staffing/create.vue'),
        meta: {
          title: '创建项目人员调配申请',
          activePath: '/bpm/oa/staffing',
        },
      },
      {
        path: 'staffing/detail',
        name: 'OAStaffingDetail',
        component: () => import('#/views/bpm/oa/staffing/detail.vue'),
        meta: {
          title: '项目人员调配申请详情',
          activePath: '/bpm/oa/staffing',
        },
      },
    ],
  },
];

export default routes;
