import type { RouteRecordRaw } from 'vue-router';

const BasicLayout = () => import('#/layouts/basic.vue');

const routes: RouteRecordRaw[] = [
  {
    path: '/system',
    component: BasicLayout,
    meta: {
      hideInMenu: true,
      title: '系统管理',
    },
    children: [
      {
        path: 'notice',
        name: 'SystemNoticeStatic',
        component: () => import('#/views/system/notice/index.vue'),
        meta: {
          title: '通知公告',
          activePath: '/system/notice',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
