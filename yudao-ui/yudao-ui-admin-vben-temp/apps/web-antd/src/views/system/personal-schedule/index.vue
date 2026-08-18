<script lang="ts" setup>
import type {
  CalendarOptions,
  DatesSetArg,
  EventClickArg,
  EventDidMountArg,
  EventInput,
  SelectArg,
} from '@fullcalendar/core';
import type { SystemPersonalScheduleApi } from '#/api/system/personal-schedule';
import type { SystemUserApi } from '#/api/system/user';

import dayGridPlugin from '@fullcalendar/daygrid';
import interactionPlugin from '@fullcalendar/interaction';
import timeGridPlugin from '@fullcalendar/timegrid';
import FullCalendar from '@fullcalendar/vue3';
import zhCnLocale from '@fullcalendar/core/locales/zh-cn';
import dayjs from 'dayjs';
import { computed, ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { Modal, Spin } from 'ant-design-vue';

import {
  getMyPersonalCalendar,
} from '#/api/system/personal-schedule';
import { getSimpleUserList } from '#/api/system/user';

import {
  buildCalendarEventTitle,
  buildCalendarEventTooltip,
} from './data';
import Form from './modules/form.vue';

interface RangeState {
  startTime: string;
  endTime: string;
}

const calendarRef = ref<InstanceType<typeof FullCalendar>>();
const eventList = ref<SystemPersonalScheduleApi.CalendarEvent[]>([]);
const userList = ref<SystemUserApi.User[]>([]);
const loading = ref(false);
const currentRange = ref<RangeState>();
const keyword = ref('');
const sourceFilter = ref<'ALL' | SystemPersonalScheduleApi.CalendarEventSourceType>('ALL');

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

function normalizeSelection(info: SelectArg) {
  if (!info.allDay) {
    return {
      startTime: dayjs(info.start).format('YYYY-MM-DD HH:mm:ss'),
      endTime: dayjs(info.end).format('YYYY-MM-DD HH:mm:ss'),
    };
  }
  const base = dayjs(info.start).hour(9).minute(0).second(0);
  return {
    startTime: base.format('YYYY-MM-DD HH:mm:ss'),
    endTime: base.add(1, 'hour').format('YYYY-MM-DD HH:mm:ss'),
  };
}

function openCreateModal(initialValues?: Partial<SystemPersonalScheduleApi.PersonalSchedule>) {
  formModalApi
    .setData({
      initialValues,
      userOptions: userList.value,
    })
    .open();
}

function openEditModal(schedule: SystemPersonalScheduleApi.PersonalSchedule) {
  formModalApi
    .setData({
      schedule,
      userOptions: userList.value,
    })
    .open();
}

async function loadCalendar(range?: RangeState) {
  if (!range) {
    return;
  }
  loading.value = true;
  try {
    eventList.value = await getMyPersonalCalendar(range);
  } finally {
    loading.value = false;
  }
}

async function handleDatesSet(info: DatesSetArg) {
  currentRange.value = {
    startTime: dayjs(info.start).format('YYYY-MM-DD HH:mm:ss'),
    endTime: dayjs(info.end).format('YYYY-MM-DD HH:mm:ss'),
  };
  await loadCalendar(currentRange.value);
}

function handleSelect(info: SelectArg) {
  openCreateModal(normalizeSelection(info));
}

function handleCreateNow() {
  openCreateModal();
}

function handleEventClick(info: EventClickArg) {
  const data = info.event.extendedProps.raw as SystemPersonalScheduleApi.CalendarEvent;
  if (data.sourceType === 'MEETING_BOOKING') {
    Modal.info({
      title: '会议室预定详情',
      content: [
        `时间：${dayjs(data.startTime).format('YYYY-MM-DD HH:mm')} - ${dayjs(data.endTime).format('YYYY-MM-DD HH:mm')}`,
        `标题：${data.title}`,
        data.meetingRoomName ? `会议室：${data.meetingRoomName}` : '',
        data.attendeeUserNicknames?.length
          ? `参与者：${data.attendeeUserNicknames.join('、')}`
          : '',
        data.description ? `备注：${data.description}` : '',
        '该事件来自会议室预定，仅在本日历中只读展示。',
      ]
        .filter(Boolean)
        .join('\n'),
    });
    return;
  }
  openEditModal({
    id: data.sourceId,
    title: data.title,
    startTime: data.startTime,
    endTime: data.endTime,
    location: data.location,
    description: data.description,
    attendeeUserIds: data.attendeeUserIds,
    attendeeUserNicknames: data.attendeeUserNicknames,
    otherParticipants: data.otherParticipants,
  });
}

function handleEventDidMount(info: EventDidMountArg) {
  const data = info.event.extendedProps.raw as SystemPersonalScheduleApi.CalendarEvent;
  info.el.title = buildCalendarEventTooltip(data);
}

function isVisibleEvent(event: SystemPersonalScheduleApi.CalendarEvent) {
  const sourceMatched =
    sourceFilter.value === 'ALL' || event.sourceType === sourceFilter.value;
  if (!sourceMatched) {
    return false;
  }
  const text = keyword.value.trim();
  if (!text) {
    return true;
  }
  return [
    event.title,
    event.location,
    event.description,
    event.meetingRoomName,
    ...(event.attendeeUserNicknames || []),
    event.otherParticipants,
  ]
    .filter(Boolean)
    .some((item) => String(item).includes(text));
}

const calendarEvents = computed<EventInput[]>(() =>
  eventList.value
    .filter(isVisibleEvent)
    .map((item) => ({
      id: `${item.sourceType}-${item.sourceId}`,
      title: buildCalendarEventTitle(item),
      start: item.startTime,
      end: item.endTime,
      backgroundColor:
        item.sourceType === 'PERSONAL_SCHEDULE' ? '#2563eb' : '#f59e0b',
      borderColor:
        item.sourceType === 'PERSONAL_SCHEDULE' ? '#1d4ed8' : '#d97706',
      textColor: '#ffffff',
      extendedProps: {
        raw: item,
      },
    })),
);

const calendarOptions = computed<CalendarOptions>(() => ({
  plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
  locale: zhCnLocale,
  initialView: 'dayGridMonth',
  headerToolbar: false,
  buttonText: {
    today: '今天',
  },
  firstDay: 1,
  dayMaxEvents: true,
  selectable: true,
  selectMirror: true,
  editable: false,
  nowIndicator: true,
  height: 'auto',
  events: calendarEvents.value,
  datesSet: handleDatesSet,
  select: handleSelect,
  eventClick: handleEventClick,
  eventDidMount: handleEventDidMount,
  allDaySlot: false,
  // 会议室预定支持 00:00-24:00 的两小时整点时段，日/周视图需覆盖完整范围。
  slotMinTime: '00:00:00',
  slotMaxTime: '24:00:00',
  scrollTime: '06:00:00',
}));

function getCalendarApi() {
  return calendarRef.value?.getApi();
}

function changeView(viewName: 'dayGridMonth' | 'timeGridDay' | 'timeGridWeek') {
  getCalendarApi()?.changeView(viewName);
}

function goToday() {
  getCalendarApi()?.today();
}

function goPrev() {
  getCalendarApi()?.prev();
}

function goNext() {
  getCalendarApi()?.next();
}

async function handleRefresh() {
  await loadCalendar(currentRange.value);
}

async function handleModalSuccess() {
  await handleRefresh();
}

getSimpleUserList().then((data) => {
  userList.value = data;
});
</script>

<template>
  <Page auto-content-height title="个人日程">
    <FormModal @success="handleModalSuccess" />
    <div class="personal-schedule-page">
      <div class="toolbar">
        <div class="toolbar-left">
          <a-button type="primary" @click="handleCreateNow">新增日程</a-button>
          <a-button @click="goToday">今天</a-button>
          <a-button @click="goPrev">上一段</a-button>
          <a-button @click="goNext">下一段</a-button>
        </div>
        <div class="toolbar-right">
          <a-input
            v-model:value="keyword"
            allow-clear
            placeholder="搜索标题、地址、参与者"
            style="width: 240px"
          />
          <a-select
            v-model:value="sourceFilter"
            style="width: 160px"
            :options="[
              { label: '全部事件', value: 'ALL' },
              { label: '个人日程', value: 'PERSONAL_SCHEDULE' },
              { label: '会议室预定', value: 'MEETING_BOOKING' },
            ]"
          />
          <a-button @click="changeView('timeGridDay')">日视图</a-button>
          <a-button @click="changeView('timeGridWeek')">周视图</a-button>
          <a-button @click="changeView('dayGridMonth')">月视图</a-button>
        </div>
      </div>

      <div class="legend">
        <span class="legend-item">
          <span class="legend-dot legend-dot--personal"></span>
          个人日程
        </span>
        <span class="legend-item">
          <span class="legend-dot legend-dot--meeting"></span>
          我的会议室预定（只读）
        </span>
      </div>

      <a-spin :spinning="loading">
        <div class="calendar-shell">
          <FullCalendar ref="calendarRef" :options="calendarOptions" />
        </div>
      </a-spin>
    </div>
  </Page>
</template>

<style scoped>
.personal-schedule-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.legend {
  display: flex;
  gap: 16px;
  align-items: center;
  color: #475569;
  font-size: 13px;
}

.legend-item {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.legend-dot--personal {
  background: #2563eb;
}

.legend-dot--meeting {
  background: #f59e0b;
}

.calendar-shell {
  padding: 16px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 10px 30px rgb(15 23 42 / 0.06);
}

:deep(.fc) {
  --fc-border-color: #e2e8f0;
  --fc-page-bg-color: #ffffff;
  --fc-neutral-bg-color: #f8fafc;
  --fc-today-bg-color: #eff6ff;
  --fc-button-bg-color: #2563eb;
  --fc-button-border-color: #2563eb;
  --fc-button-hover-bg-color: #1d4ed8;
  --fc-button-hover-border-color: #1d4ed8;
  --fc-button-active-bg-color: #1e40af;
  --fc-button-active-border-color: #1e40af;
  --fc-event-border-width: 0;
  --fc-event-text-color: #ffffff;
  font-size: 13px;
}

:deep(.fc .fc-toolbar-title) {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

:deep(.fc .fc-event-title) {
  white-space: normal;
}

:deep(.fc .fc-daygrid-event) {
  border-radius: 10px;
  padding: 2px 6px;
}

:deep(.fc .fc-timegrid-event) {
  border-radius: 12px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-left,
  .toolbar-right {
    width: 100%;
  }
}
</style>
