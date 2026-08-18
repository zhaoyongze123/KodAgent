<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemMeetingBookingApi } from '#/api/system/meeting-booking';
import type { SystemMeetingRoomApi } from '#/api/system/meeting-room';
import type { SystemUserApi } from '#/api/system/user';

import { computed, onMounted, ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';
import { message } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  cancelMyMeetingBooking,
  deleteMeetingBooking,
  getMeetingBookingPage,
  getMyMeetingBookingPage,
} from '#/api/system/meeting-booking';
import { getSimpleMeetingRoomList } from '#/api/system/meeting-room';
import { getSimpleUserList } from '#/api/system/user';
import { isAdminUser } from '#/utils/oa-user';

import { useBookingGridColumns, useBookingGridFormSchema } from './data';
import Form from './modules/form.vue';

const roomList = ref<SystemMeetingRoomApi.MeetingRoomSimple[]>([]);
const userList = ref<SystemUserApi.User[]>([]);
const userStore = useUserStore();
const isAdminView = computed(() => isAdminUser(userStore.userRoles || []));
const viewMode = ref<'admin' | 'mine'>(isAdminView.value ? 'admin' : 'mine');

const roomOptions = computed(() =>
  roomList.value.map((item) => ({
    label: `${item.name}${item.location ? ` (${item.location})` : ''}`,
    value: item.id,
  })),
);
const userOptions = computed(() =>
  userList.value.map((item) => ({
    label: item.nickname,
    value: item.id!,
  })),
);

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

async function loadOptions() {
  roomList.value = await getSimpleMeetingRoomList();
  userList.value = await getSimpleUserList();
  gridApi.formApi.setState({
    schema: useBookingGridFormSchema(roomOptions.value, userOptions.value),
  });
}

function handleRefresh() {
  gridApi.query();
}

function handleCreate() {
  formModalApi
    .setData({
      roomOptions: roomList.value,
      userOptions: userList.value,
      mode: viewMode.value,
    })
    .open();
}

function handleEdit(row: SystemMeetingBookingApi.MeetingBooking) {
  formModalApi
    .setData({
      booking: row,
      roomOptions: roomList.value,
      userOptions: userList.value,
      mode: viewMode.value,
    })
    .open();
}

async function handleCancel(row: SystemMeetingBookingApi.MeetingBooking) {
  const hideLoading = message.loading({
    content: '正在取消预定...',
    duration: 0,
  });
  try {
    await cancelMyMeetingBooking(row.id!);
    message.success('已取消');
    handleRefresh();
  } finally {
    hideLoading();
  }
}

async function handleDelete(row: SystemMeetingBookingApi.MeetingBooking) {
  const hideLoading = message.loading({
    content: '正在删除预定...',
    duration: 0,
  });
  try {
    await deleteMeetingBooking(row.id!);
    message.success('已删除');
    handleRefresh();
  } finally {
    hideLoading();
  }
}

function switchViewMode(mode: 'admin' | 'mine') {
  if (mode === 'admin' && !isAdminView.value) {
    return;
  }
  viewMode.value = mode;
  handleRefresh();
}

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: [],
  },
  gridOptions: {
    columns: useBookingGridColumns(),
    height: 'auto',
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          const params = {
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          };
          return viewMode.value === 'mine'
            ? await getMyMeetingBookingPage(params)
            : await getMeetingBookingPage(params);
        },
      },
    },
    rowConfig: {
      keyField: 'id',
      isHover: true,
    },
    toolbarConfig: {
      refresh: true,
      search: true,
    },
  } as VxeTableGridOptions<SystemMeetingBookingApi.MeetingBooking>,
});

onMounted(loadOptions);
</script>

<template>
  <Page auto-content-height title="会议室预定">
    <FormModal @success="handleRefresh" />
    <div class="mb-3 flex gap-2">
      <a-button
        v-if="isAdminView"
        type="primary"
        :ghost="viewMode !== 'admin'"
        @click="switchViewMode('admin')"
      >
        全部预定
      </a-button>
      <a-button
        type="primary"
        :ghost="viewMode !== 'mine'"
        @click="switchViewMode('mine')"
      >
        我的预定
      </a-button>
    </div>
    <Grid table-title="预定列表">
      <template #toolbar-tools>
        <TableAction
          :actions="[
            {
              label: '新建预定',
              type: 'primary',
              icon: ACTION_ICON.ADD,
              onClick: handleCreate,
            },
          ]"
        />
      </template>
      <template #actions="{ row }">
        <TableAction
          :actions="[
            {
              label: '编辑',
              type: 'link',
              icon: ACTION_ICON.EDIT,
              onClick: handleEdit.bind(null, row),
            },
            ...(viewMode === 'mine'
              ? [
                  {
                    label: '取消',
                    type: 'link' as const,
                    danger: true,
                    icon: ACTION_ICON.DELETE,
                    onClick: handleCancel.bind(null, row),
                  },
                ]
              : [
                  {
                    label: '删除',
                    type: 'link' as const,
                    danger: true,
                    icon: ACTION_ICON.DELETE,
                    onClick: handleDelete.bind(null, row),
                  },
                ]),
          ]"
        />
      </template>
    </Grid>
  </Page>
</template>
