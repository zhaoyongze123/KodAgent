import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/oa-lite',
    name: 'OALite',
    redirect: (to) => ({
      path: '/oa-lite/center',
      query: { ...to.query, view: 'create' },
    }),
    meta: {
      title: '发起审批',
      hideInMenu: true,
      hideInTab: true,
    },
  },
  {
    path: '/oa-lite/center',
    name: 'OALiteCenter',
    component: () => import('#/views/oa-lite/index.vue'),
    meta: {
      title: '审批中心',
      hideInMenu: true,
      hideInTab: true,
    },
  },
  {
    path: '/oa-lite/notifications',
    name: 'OALiteNotifications',
    component: () => import('#/views/oa-lite/notifications.vue'),
    meta: {
      title: 'OA 通知中心',
      hideInMenu: true,
      hideInTab: true,
    },
  },
];

export default routes;
