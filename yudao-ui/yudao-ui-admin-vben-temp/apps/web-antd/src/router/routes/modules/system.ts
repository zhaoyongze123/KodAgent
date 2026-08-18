import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/system/notify-message',
    component: () => import('#/views/system/notify/my/index.vue'),
    name: 'MyNotifyMessage',
    meta: {
      title: '我的站内信',
      icon: 'ant-design:message-filled',
      hideInMenu: true,
    },
  },
  {
    path: '/system/my-party-file',
    redirect: '/party-file/my',
    name: 'MyPartyFile',
    meta: {
      title: '我的党务文件',
      icon: 'ant-design:file-text-filled',
      hideInMenu: true,
    },
  },
];

export default routes;
