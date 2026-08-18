import type { RouteRecordRaw } from 'vue-router';

const BasicLayout = () => import('#/layouts/basic.vue');

const routes: RouteRecordRaw[] = [
  {
    path: '/schedule',
    component: BasicLayout,
    redirect: '/schedule/calendar',
    meta: {
      hideInMenu: true,
      title: '日程',
    },
    children: [
      {
        path: 'calendar',
        name: 'ScheduleCenterCalendarStatic',
        component: () => import('#/views/system/personal-schedule/index.vue'),
        meta: {
          title: '个人日程',
          activePath: '/schedule/calendar',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
