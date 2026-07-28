import type { RouteRecordRaw } from 'vue-router';

const BasicLayout = () => import('#/layouts/basic.vue');

const routes: RouteRecordRaw[] = [
  {
    path: '/meeting-room',
    component: BasicLayout,
    redirect: '/meeting-room/booking',
    meta: {
      hideInMenu: true,
      title: '会议室',
    },
    children: [
      {
        path: 'manage',
        name: 'MeetingCenterManageStatic',
        component: () => import('#/views/system/meeting-room/index.vue'),
        meta: {
          title: '会议室管理',
          activePath: '/meeting-room/manage',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'booking',
        name: 'MeetingCenterBookingStatic',
        component: () => import('#/views/system/meeting-booking/index.vue'),
        meta: {
          title: '会议室预定',
          activePath: '/meeting-room/booking',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'schedule',
        name: 'MeetingCenterScheduleStatic',
        component: () => import('#/views/system/meeting-booking/schedule.vue'),
        meta: {
          title: '会议室排期',
          activePath: '/meeting-room/schedule',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
