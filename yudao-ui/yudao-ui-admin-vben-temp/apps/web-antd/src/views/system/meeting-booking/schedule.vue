<script lang="ts" setup>
import type { SystemMeetingBookingApi } from '#/api/system/meeting-booking';
import type { SystemMeetingRoomApi } from '#/api/system/meeting-room';
import type { SystemUserApi } from '#/api/system/user';

import dayjs from 'dayjs';
import { computed, onMounted, ref, watch } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { message } from 'ant-design-vue';

import {
  getMonthSchedule,
  getWeekSchedule,
} from '#/api/system/meeting-booking';
import { getSimpleMeetingRoomList } from '#/api/system/meeting-room';
import { getSimpleUserList } from '#/api/system/user';

import Form from './modules/form.vue';

type ViewMode = 'month' | 'week';

interface ScheduleDisplayBooking {
  booking: SystemMeetingBookingApi.MeetingBooking;
  hiddenConflicts: SystemMeetingBookingApi.MeetingBooking[];
}

const viewMode = ref<ViewMode>('week');
const roomList = ref<SystemMeetingRoomApi.MeetingRoomSimple[]>([]);
const userList = ref<SystemUserApi.User[]>([]);
const list = ref<SystemMeetingBookingApi.MeetingBooking[]>([]);
const loading = ref(false);
const currentDate = ref(dayjs());

const form = ref({
  meetingRoomId: undefined as number | undefined,
  applicantUserId: undefined as number | undefined,
  subject: '',
});

const roomOptions = computed(() =>
  roomList.value.map((item) => ({
    label: item.location ? `${item.name} (${item.location})` : item.name,
    value: item.id,
  })),
);

const userOptions = computed(() =>
  userList.value.map((item) => ({
    label: item.nickname,
    value: item.id,
  })),
);

const roomNameMap = computed(() =>
  new Map(roomList.value.map((item) => [item.id, item.name])),
);

const userNameMap = computed(() =>
  new Map(userList.value.map((item) => [item.id, item.nickname])),
);

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

const scheduleRangeLabel = computed(() => {
  if (viewMode.value === 'week') {
    const start = weekDays.value[0] ?? currentDate.value.startOf('week');
    const end = weekDays.value[6] ?? currentDate.value.startOf('week').add(6, 'day');
    return `${start.format('YYYY.MM.DD')}-${end.format('MM.DD')}`;
  }
  return currentDate.value.format('YYYY.MM');
});

const weekDays = computed(() => {
  const weekStart = currentDate.value.startOf('week');
  return Array.from({ length: 7 }, (_, index) => weekStart.add(index, 'day'));
});

const monthDays = computed(() => {
  const start = currentDate.value.startOf('month');
  const end = currentDate.value.endOf('month');
  const days: dayjs.Dayjs[] = [];
  let cursor = start;
  while (cursor.isBefore(end) || cursor.isSame(end, 'day')) {
    days.push(cursor);
    cursor = cursor.add(1, 'day');
  }
  return days;
});

const filteredRoomList = computed(() => {
  if (!form.value.meetingRoomId) {
    return roomList.value;
  }
  return roomList.value.filter((item) => item.id === form.value.meetingRoomId);
});

const roomDayBookingMap = computed(() => buildRoomDayBookingMap(list.value));

const weekMatrix = computed(() => {
  return filteredRoomList.value.map((room) => ({
    room,
    cells: weekDays.value.map((day) => {
      const key = `${room.id}-${day.format('YYYY-MM-DD')}`;
      return roomDayBookingMap.value.get(key) || [];
    }),
  }));
});

const monthSummary = computed(() => {
  const summaryMap = new Map<string, ScheduleDisplayBooking[]>();
  for (const group of roomDayBookingMap.value.values()) {
    for (const item of group) {
      const key = dayjs(item.booking.startTime).format('YYYY-MM-DD');
      const dayGroup = summaryMap.get(key) || [];
      dayGroup.push(item);
      summaryMap.set(key, dayGroup);
    }
  }
  return monthDays.value.map((day) => {
    const key = day.format('YYYY-MM-DD');
    const bookings = (summaryMap.get(key) || []).slice().sort((a, b) => {
      const startDiff =
        dayjs(a.booking.startTime).valueOf() - dayjs(b.booking.startTime).valueOf();
      if (startDiff !== 0) {
        return startDiff;
      }
      return compareBookingPriority(a.booking, b.booking);
    });
    return {
      day,
      bookings,
    };
  });
});

function buildQueryRange() {
  if (viewMode.value === 'week') {
    const start = weekDays.value[0] ?? currentDate.value.startOf('week');
    const end = weekDays.value[6] ?? currentDate.value.startOf('week').add(6, 'day');
    return {
      startTime: start.startOf('day').format('YYYY-MM-DD HH:mm:ss'),
      endTime: end.endOf('day').format('YYYY-MM-DD HH:mm:ss'),
    };
  }
  return {
    startTime: currentDate.value
      .startOf('month')
      .startOf('day')
      .format('YYYY-MM-DD HH:mm:ss'),
    endTime: currentDate.value
      .endOf('month')
      .endOf('day')
      .format('YYYY-MM-DD HH:mm:ss'),
  };
}

async function loadOptions() {
  roomList.value = await getSimpleMeetingRoomList();
  userList.value = await getSimpleUserList();
}

async function handleQuery() {
  loading.value = true;
  try {
    const range = buildQueryRange();
    const params = {
      ...form.value,
      ...range,
    };
    list.value =
      viewMode.value === 'week'
        ? await getWeekSchedule(params)
        : await getMonthSchedule(params);
  } finally {
    loading.value = false;
  }
}

function switchView(mode: ViewMode) {
  viewMode.value = mode;
}

function handlePrevious() {
  currentDate.value =
    viewMode.value === 'week'
      ? currentDate.value.subtract(1, 'week')
      : currentDate.value.subtract(1, 'month');
}

function handleNext() {
  currentDate.value =
    viewMode.value === 'week'
      ? currentDate.value.add(1, 'week')
      : currentDate.value.add(1, 'month');
}

function formatTimeRange(item: SystemMeetingBookingApi.MeetingBooking) {
  return `${dayjs(item.startTime).format('HH:mm')}-${dayjs(item.endTime).format('HH:mm')}`;
}

function getBookingCreateTimeValue(item: SystemMeetingBookingApi.MeetingBooking) {
  if (!item.createTime) {
    return Number.MAX_SAFE_INTEGER;
  }
  const value = dayjs(item.createTime).valueOf();
  return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value;
}

function compareBookingPriority(
  left: SystemMeetingBookingApi.MeetingBooking,
  right: SystemMeetingBookingApi.MeetingBooking,
) {
  const createTimeDiff =
    getBookingCreateTimeValue(left) - getBookingCreateTimeValue(right);
  if (createTimeDiff !== 0) {
    return createTimeDiff;
  }
  return (left.id ?? Number.MAX_SAFE_INTEGER) - (right.id ?? Number.MAX_SAFE_INTEGER);
}

function compareBookingDisplayTime(
  left: SystemMeetingBookingApi.MeetingBooking,
  right: SystemMeetingBookingApi.MeetingBooking,
) {
  const startDiff = dayjs(left.startTime).valueOf() - dayjs(right.startTime).valueOf();
  if (startDiff !== 0) {
    return startDiff;
  }
  return compareBookingPriority(left, right);
}

function formatBookingDetailTime(item: SystemMeetingBookingApi.MeetingBooking) {
  return `${dayjs(item.startTime).format('YYYY-MM-DD HH:mm')}-${dayjs(item.endTime).format('HH:mm')}`;
}

function isBookingOverlap(
  left: SystemMeetingBookingApi.MeetingBooking,
  right: SystemMeetingBookingApi.MeetingBooking,
) {
  return dayjs(left.startTime).isBefore(dayjs(right.endTime))
    && dayjs(left.endTime).isAfter(dayjs(right.startTime));
}

function buildVisibleBookings(
  bookings: SystemMeetingBookingApi.MeetingBooking[],
): ScheduleDisplayBooking[] {
  const visibleBookings: ScheduleDisplayBooking[] = [];
  const ordered = bookings.slice().sort(compareBookingPriority);
  for (const booking of ordered) {
    const conflictOwner = visibleBookings.find((item) =>
      isBookingOverlap(item.booking, booking),
    );
    if (!conflictOwner) {
      visibleBookings.push({
        booking,
        hiddenConflicts: [],
      });
      continue;
    }
    conflictOwner.hiddenConflicts.push(booking);
  }
  for (const item of visibleBookings) {
    item.hiddenConflicts.sort(compareBookingDisplayTime);
  }
  return visibleBookings.sort((left, right) =>
    compareBookingDisplayTime(left.booking, right.booking),
  );
}

function buildRoomDayBookingMap(bookings: SystemMeetingBookingApi.MeetingBooking[]) {
  const rawMap = new Map<string, SystemMeetingBookingApi.MeetingBooking[]>();
  for (const booking of bookings) {
    const dayKey = dayjs(booking.startTime).format('YYYY-MM-DD');
    const key = `${booking.meetingRoomId}-${dayKey}`;
    const group = rawMap.get(key) || [];
    group.push(booking);
    rawMap.set(key, group);
  }
  const displayMap = new Map<string, ScheduleDisplayBooking[]>();
  for (const [key, group] of rawMap.entries()) {
    displayMap.set(key, buildVisibleBookings(group));
  }
  return displayMap;
}

function resolveApplicantName(item: SystemMeetingBookingApi.MeetingBooking) {
  return item.applicantUserNickname || '未知申请人';
}

function resolveBookingToneStyle(item: SystemMeetingBookingApi.MeetingBooking) {
  const slotIndex = Math.floor(dayjs(item.startTime).hour() / 2);
  const hue = (slotIndex * 29 + 16) % 360;
  return {
    '--booking-accent': `hsl(${hue} 82% 58%)`,
    '--booking-bg': `hsl(${hue} 100% 97%)`,
    '--booking-text': `hsl(${hue} 62% 38%)`,
    '--booking-muted': `hsl(${hue} 28% 46%)`,
  };
}

function resolveMeetingRoomName(item: SystemMeetingBookingApi.MeetingBooking) {
  return item.meetingRoomName || roomNameMap.value.get(item.meetingRoomId) || '-';
}

function resolveAttendeeNames(item: SystemMeetingBookingApi.MeetingBooking) {
  const responseNames = (item.attendeeUserNicknames || [])
    .map((name) => name?.trim())
    .filter((name): name is string => !!name);
  if (responseNames.length > 0) {
    return responseNames.join('、');
  }
  const names = (item.attendeeUserIds || [])
    .map((id) => userNameMap.value.get(id))
    .filter((name): name is string => !!name);
  return names.length > 0 ? names.join('、') : '未填写';
}

function resolveBookingRemark(item: SystemMeetingBookingApi.MeetingBooking) {
  return item.remark?.trim() || '无';
}

function resolveWeekDay(index: number) {
  return weekDays.value[index] ?? currentDate.value.startOf('week').add(index, 'day');
}

function isToday(day: dayjs.Dayjs) {
  return day.isSame(dayjs(), 'day');
}

function isEndedDay(day: dayjs.Dayjs) {
  return day.endOf('day').isBefore(dayjs());
}

function openCreateModal(initialValues: {
  bookingDate: string;
  meetingRoomId?: number;
}) {
  formModalApi
    .setData({
      roomOptions: roomList.value,
      userOptions: userList.value,
      mode: 'mine',
      initialValues,
    })
    .open();
}

function handleCreateFromWeekCell(roomId: number, day: dayjs.Dayjs) {
  if (isEndedDay(day)) {
    message.warning('已结束日期不可新建预定');
    return;
  }
  openCreateModal({
    meetingRoomId: roomId,
    bookingDate: day.format('YYYY-MM-DD'),
  });
}

function handleCreateFromMonthDay(day: dayjs.Dayjs) {
  if (isEndedDay(day)) {
    message.warning('已结束日期不可新建预定');
    return;
  }
  openCreateModal({
    bookingDate: day.format('YYYY-MM-DD'),
  });
}

function handleCreateFromBooking(item: SystemMeetingBookingApi.MeetingBooking) {
  const bookingDay = dayjs(item.startTime);
  if (isEndedDay(bookingDay)) {
    message.warning('已结束日期不可新建预定');
    return;
  }
  openCreateModal({
    meetingRoomId: item.meetingRoomId,
    bookingDate: bookingDay.format('YYYY-MM-DD'),
  });
}

async function handleCreateSuccess() {
  await handleQuery();
}

watch([viewMode, currentDate], () => {
  handleQuery();
});

onMounted(async () => {
  try {
    await loadOptions();
    await handleQuery();
  } catch (error) {
    message.error('加载会议室排期失败');
    throw error;
  }
});
</script>

<template>
  <Page auto-content-height title="会议室排期">
    <FormModal @success="handleCreateSuccess" />
    <div class="schedule-page">
      <div class="schedule-toolbar">
        <div class="schedule-filters">
          <a-select
            v-model:value="form.meetingRoomId"
            allow-clear
            placeholder="会议室"
            :options="roomOptions"
          />
          <a-select
            v-model:value="form.applicantUserId"
            allow-clear
            placeholder="申请人"
            :options="userOptions"
          />
          <a-input
            v-model:value="form.subject"
            allow-clear
            placeholder="会议主题"
          />
        </div>
        <div class="schedule-actions">
          <a-button
            type="primary"
            :ghost="viewMode !== 'week'"
            @click="switchView('week')"
          >
            周视图
          </a-button>
          <a-button
            type="primary"
            :ghost="viewMode !== 'month'"
            @click="switchView('month')"
          >
            月视图
          </a-button>
          <a-button type="primary" @click="handleQuery">查询排期</a-button>
        </div>
      </div>

      <div class="schedule-header-card">
        <div class="schedule-range-switch">
          <a-button type="text" @click="handlePrevious">
            <span class="range-arrow">&lt;</span>
          </a-button>
          <span class="range-label">{{ scheduleRangeLabel }}</span>
          <a-button type="text" @click="handleNext">
            <span class="range-arrow">&gt;</span>
          </a-button>
        </div>
        <div class="schedule-tip">点击排期格子可快速发起预定</div>
      </div>

      <div v-if="viewMode === 'week'" class="week-board" v-loading="loading">
        <table class="week-table">
          <thead>
            <tr>
              <th class="room-column">会议/星期</th>
              <th
                v-for="day in weekDays"
                :key="day.format('YYYY-MM-DD')"
                :class="{ 'is-today-column': isToday(day) }"
              >
                <div class="day-head">
                  <span>{{ day.format('dd') }}</span>
                  <div class="day-date-line">
                    <span>{{ day.format('MM.DD') }}</span>
                    <span v-if="isToday(day)" class="today-badge">今日</span>
                  </div>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in weekMatrix" :key="row.room.id">
              <td class="room-name-cell">
                {{ row.room.name }}
              </td>
              <td
                v-for="(cell, index) in row.cells"
                :key="`${row.room.id}-${weekDays[index]?.format('YYYY-MM-DD')}`"
                class="schedule-cell"
                :class="{ 'is-today-column': isToday(resolveWeekDay(index)) }"
                @click="handleCreateFromWeekCell(row.room.id, resolveWeekDay(index))"
              >
                <div v-if="cell.length" class="booking-list">
                  <a-popover
                    v-for="item in cell"
                    :key="item.booking.id"
                    trigger="hover"
                    placement="topLeft"
                    overlay-class-name="booking-detail-popover"
                  >
                    <template #content>
                      <div
                        class="booking-detail-card"
                        :style="resolveBookingToneStyle(item.booking)"
                      >
                        <div class="booking-detail-title">{{ item.booking.subject }}</div>
                        <div class="booking-detail-row">
                          <span class="booking-detail-label">时间</span>
                          <span class="booking-detail-value">
                            {{ formatBookingDetailTime(item.booking) }}
                          </span>
                        </div>
                        <div class="booking-detail-row">
                          <span class="booking-detail-label">会议室</span>
                          <span class="booking-detail-value">
                            {{ resolveMeetingRoomName(item.booking) }}
                          </span>
                        </div>
                        <div class="booking-detail-row">
                          <span class="booking-detail-label">申请人</span>
                          <span class="booking-detail-value">
                            {{ resolveApplicantName(item.booking) }}
                          </span>
                        </div>
                        <div class="booking-detail-row">
                          <span class="booking-detail-label">参会人</span>
                          <span class="booking-detail-value">
                            {{ resolveAttendeeNames(item.booking) }}
                          </span>
                        </div>
                        <div class="booking-detail-row">
                          <span class="booking-detail-label">备注</span>
                          <span class="booking-detail-value">
                            {{ resolveBookingRemark(item.booking) }}
                          </span>
                        </div>
                        <div
                          v-if="item.hiddenConflicts.length > 0"
                          class="booking-conflict-section"
                        >
                          <div class="booking-conflict-title">
                            已隐藏冲突预定 {{ item.hiddenConflicts.length }} 条
                          </div>
                          <div
                            v-for="conflict in item.hiddenConflicts"
                            :key="conflict.id"
                            class="booking-conflict-item"
                          >
                            <div class="booking-conflict-time">
                              {{ formatTimeRange(conflict) }}
                            </div>
                            <div class="booking-conflict-subject">
                              {{ conflict.subject }}
                            </div>
                            <div class="booking-conflict-applicant">
                              {{ resolveApplicantName(conflict) }}
                            </div>
                          </div>
                        </div>
                      </div>
                    </template>
                    <div
                      class="booking-chip"
                      :style="resolveBookingToneStyle(item.booking)"
                      :title="`${formatTimeRange(item.booking)} ${item.booking.subject}`"
                      @click.stop="handleCreateFromBooking(item.booking)"
                    >
                      <div class="booking-time">
                        {{ formatTimeRange(item.booking) }}
                      </div>
                      <div class="booking-subject">
                        {{ item.booking.subject }}
                      </div>
                      <div class="booking-applicant">
                        {{ resolveApplicantName(item.booking) }}
                      </div>
                    </div>
                  </a-popover>
                </div>
                <div v-else class="empty-cell">点击预定</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="month-board">
        <div class="month-grid">
          <div
            v-for="item in monthSummary"
            :key="item.day.format('YYYY-MM-DD')"
            class="month-day-card"
            :class="{ 'is-today-card': isToday(item.day) }"
            @click="handleCreateFromMonthDay(item.day)"
          >
            <div class="month-day-head">
              <span
                class="month-day-date"
                :class="{ 'is-today-date': isToday(item.day) }"
              >
                {{ item.day.format('DD') }}
              </span>
              <span class="month-day-week">{{ item.day.format('dd') }}</span>
            </div>
            <div v-if="isToday(item.day)" class="month-today-badge">今日</div>
            <div v-if="item.bookings.length" class="month-day-body">
              <a-popover
                v-for="booking in item.bookings"
                :key="booking.booking.id"
                trigger="hover"
                placement="topLeft"
                overlay-class-name="booking-detail-popover"
              >
                <template #content>
                  <div
                    class="booking-detail-card"
                    :style="resolveBookingToneStyle(booking.booking)"
                  >
                    <div class="booking-detail-title">{{ booking.booking.subject }}</div>
                    <div class="booking-detail-row">
                      <span class="booking-detail-label">时间</span>
                      <span class="booking-detail-value">
                        {{ formatBookingDetailTime(booking.booking) }}
                      </span>
                    </div>
                    <div class="booking-detail-row">
                      <span class="booking-detail-label">会议室</span>
                      <span class="booking-detail-value">
                        {{ resolveMeetingRoomName(booking.booking) }}
                      </span>
                    </div>
                    <div class="booking-detail-row">
                      <span class="booking-detail-label">申请人</span>
                      <span class="booking-detail-value">
                        {{ resolveApplicantName(booking.booking) }}
                      </span>
                    </div>
                    <div class="booking-detail-row">
                      <span class="booking-detail-label">参会人</span>
                      <span class="booking-detail-value">
                        {{ resolveAttendeeNames(booking.booking) }}
                      </span>
                    </div>
                    <div class="booking-detail-row">
                      <span class="booking-detail-label">备注</span>
                      <span class="booking-detail-value">
                        {{ resolveBookingRemark(booking.booking) }}
                      </span>
                    </div>
                    <div
                      v-if="booking.hiddenConflicts.length > 0"
                      class="booking-conflict-section"
                    >
                      <div class="booking-conflict-title">
                        已隐藏冲突预定 {{ booking.hiddenConflicts.length }} 条
                      </div>
                      <div
                        v-for="conflict in booking.hiddenConflicts"
                        :key="conflict.id"
                        class="booking-conflict-item"
                      >
                        <div class="booking-conflict-time">
                          {{ formatTimeRange(conflict) }}
                        </div>
                        <div class="booking-conflict-subject">
                          {{ conflict.subject }}
                        </div>
                        <div class="booking-conflict-applicant">
                          {{ resolveApplicantName(conflict) }}
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <div
                  class="month-booking-item"
                  :style="resolveBookingToneStyle(booking.booking)"
                  @click.stop="handleCreateFromBooking(booking.booking)"
                >
                  <div>{{ formatTimeRange(booking.booking) }}</div>
                  <div>{{ resolveMeetingRoomName(booking.booking) }}</div>
                  <div class="month-booking-subject">{{ booking.booking.subject }}</div>
                </div>
              </a-popover>
            </div>
            <div v-else class="month-empty">暂无预定</div>
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.schedule-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.schedule-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
}

.schedule-filters {
  display: grid;
  flex: 1;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.schedule-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.schedule-header-card {
  border: 1px solid #e5eaf3;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
  padding: 16px 20px;
}

.schedule-tip {
  margin-top: 10px;
  text-align: center;
  color: #7a8aa6;
  font-size: 13px;
}

.schedule-range-switch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.range-label {
  min-width: 220px;
  text-align: center;
  font-size: 26px;
  font-weight: 600;
  color: #1f2a44;
}

.range-arrow {
  font-size: 20px;
  color: #5b6b88;
}

.week-board {
  overflow-x: auto;
  border: 1px solid #e6ebf5;
  border-radius: 12px;
  background: #fff;
}

.week-table {
  width: 100%;
  min-width: 1080px;
  border-collapse: collapse;
  table-layout: fixed;
}

.week-table th,
.week-table td {
  border: 1px solid #edf1f7;
  padding: 12px 10px;
  vertical-align: top;
}

.week-table th {
  background: #f8fbff;
  color: #5f6f8a;
  font-weight: 600;
  text-align: center;
}

.room-column {
  width: 180px;
}

.day-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.day-date-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.today-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #1677ff 0%, #49a3ff 100%);
  box-shadow: 0 8px 18px rgb(22 119 255 / 22%);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.room-name-cell {
  background: #fafcff;
  color: #41526b;
  font-weight: 500;
}

.week-table th.is-today-column {
  background: linear-gradient(180deg, #eef6ff 0%, #f8fbff 100%);
  box-shadow: inset 0 -2px 0 #1677ff;
}

.schedule-cell {
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.schedule-cell.is-today-column {
  background: linear-gradient(180deg, #f7fbff 0%, #eef6ff 100%);
}

.schedule-cell:hover {
  background: #f8fbff;
}

.schedule-cell.is-today-column:hover {
  background: linear-gradient(180deg, #eef6ff 0%, #e4f0ff 100%);
}

.booking-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.booking-chip {
  border-left: 3px solid var(--booking-accent, #30b2ff);
  border-radius: 8px;
  background: var(--booking-bg, #f1fbff);
  padding: 8px 10px;
  color: var(--booking-text, #1e7fb8);
  line-height: 1.45;
  cursor: help;
}

.booking-time {
  font-weight: 600;
}

.booking-subject {
  word-break: break-word;
}

.booking-applicant {
  color: var(--booking-muted, #6a87a5);
  font-size: 12px;
}

.empty-cell {
  min-height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #e0e8f5;
  border-radius: 10px;
  color: #9aa8bf;
  font-size: 12px;
}

.month-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.month-day-card {
  position: relative;
  min-height: 180px;
  border: 1px solid #e6ebf5;
  border-radius: 12px;
  background: #fff;
  padding: 14px;
  cursor: pointer;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.month-day-card:hover {
  border-color: #cfe1ff;
  box-shadow: 0 8px 18px rgb(15 42 77 / 8%);
  transform: translateY(-1px);
}

.month-day-card.is-today-card {
  border-color: #91caff;
  background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%);
  box-shadow:
    0 14px 30px rgb(22 119 255 / 10%),
    inset 0 0 0 1px rgb(22 119 255 / 10%);
}

.month-day-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.month-day-date {
  font-size: 24px;
  font-weight: 700;
  color: #1f2a44;
}

.month-day-date.is-today-date {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: linear-gradient(135deg, #1677ff 0%, #49a3ff 100%);
  box-shadow: 0 10px 24px rgb(22 119 255 / 24%);
  color: #fff;
  font-size: 20px;
}

.month-day-week {
  color: #7a8aa6;
}

.month-today-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  min-width: 42px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgb(22 119 255 / 10%);
  color: #1677ff;
  font-size: 12px;
  font-weight: 600;
}

.month-day-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.month-booking-item {
  border-left: 3px solid var(--booking-accent, #30b2ff);
  border-radius: 8px;
  background: var(--booking-bg, #f5fbff);
  padding: 8px 10px;
  color: var(--booking-text, #245f8c);
  line-height: 1.5;
  cursor: help;
}

.month-booking-subject {
  color: #1677ff;
}

.month-empty {
  color: #9aa8bf;
  font-size: 13px;
}

:deep(.booking-detail-popover .ant-popover-inner) {
  padding: 0;
  border-radius: 14px;
}

.booking-detail-card {
  width: 320px;
  padding: 14px 16px;
  border-top: 3px solid var(--booking-accent, #30b2ff);
  background: linear-gradient(180deg, #ffffff 0%, var(--booking-bg, #f7fbff) 100%);
}

.booking-detail-title {
  margin-bottom: 12px;
  color: #17395c;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  word-break: break-word;
}

.booking-detail-row {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 8px;
  align-items: start;
  padding-top: 8px;
  color: #3b516d;
  font-size: 13px;
}

.booking-detail-row + .booking-detail-row {
  border-top: 1px solid #eaf1fb;
}

.booking-detail-label {
  color: #7c8ca6;
}

.booking-detail-value {
  line-height: 1.6;
  word-break: break-word;
}

.booking-conflict-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #dbe8f8;
}

.booking-conflict-title {
  margin-bottom: 8px;
  color: #d46b08;
  font-size: 12px;
  font-weight: 600;
}

.booking-conflict-item + .booking-conflict-item {
  margin-top: 8px;
}

.booking-conflict-time {
  color: #17395c;
  font-size: 12px;
  font-weight: 600;
}

.booking-conflict-subject {
  color: #41526b;
  font-size: 12px;
}

.booking-conflict-applicant {
  color: #7a8aa6;
  font-size: 12px;
}

@media (max-width: 768px) {
  .range-label {
    min-width: auto;
    font-size: 20px;
  }

  .schedule-toolbar {
    flex-direction: column;
  }

  .schedule-actions {
    justify-content: flex-start;
  }
}
</style>
