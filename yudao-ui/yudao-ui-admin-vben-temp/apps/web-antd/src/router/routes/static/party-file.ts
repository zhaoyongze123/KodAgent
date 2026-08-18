import type { RouteRecordRaw } from 'vue-router';

const BasicLayout = () => import('#/layouts/basic.vue');

const routes: RouteRecordRaw[] = [
  {
    path: '/party-file',
    component: BasicLayout,
    redirect: '/party-file/my',
    meta: {
      hideInMenu: true,
      title: '党务管理',
    },
    children: [
      {
        path: 'manage',
        name: 'PartyFileCenterManageStatic',
        component: () => import('#/views/system/party-file/index.vue'),
        meta: {
          title: '党务文件管理',
          activePath: '/party-file/manage',
          hideInMenu: true,
          keepAlive: true,
        },
      },
      {
        path: 'my',
        name: 'PartyFileCenterMyStatic',
        component: () => import('#/views/system/party-file/my-index.vue'),
        meta: {
          title: '我的党务文件',
          activePath: '/party-file/my',
          hideInMenu: true,
          keepAlive: true,
        },
      },
    ],
  },
];

export default routes;
