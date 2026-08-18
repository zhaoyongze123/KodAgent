<script lang="ts" setup>
import type { SystemMeetingBookingApi } from '#/api/system/meeting-booking';
import type { SystemMeetingRoomApi } from '#/api/system/meeting-room';
import type { SystemUserApi } from '#/api/system/user';

import dayjs from 'dayjs';
import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { message, Modal as AntModal } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  checkMeetingBookingConflict,
  createMeetingBooking,
  getMeetingBooking,
  updateMeetingBooking,
  updateMyMeetingBooking,
} from '#/api/system/meeting-booking';
import { $t } from '#/locales';

import { useBookingFormSchema } from '../data';

const emit = defineEmits(['success']);

type Mode = 'admin' | 'mine';

interface ModalData {
  booking?: SystemMeetingBookingApi.MeetingBooking;
  roomOptions: SystemMeetingRoomApi.MeetingRoomSimple[];
  userOptions: SystemUserApi.User[];
  mode?: Mode;
  initialValues?: MeetingBookingFormValues;
}

interface MeetingBookingFormValues
  extends Partial<SystemMeetingBookingApi.MeetingBooking> {
  bookingDate?: string;
  timeSlot?: string;
}

const ALL_TIME_SLOTS = [
  '00:00-02:00',
  '02:00-04:00',
  '04:00-06:00',
  '06:00-08:00',
  '08:00-10:00',
  '10:00-12:00',
  '12:00-14:00',
  '14:00-16:00',
  '16:00-18:00',
  '18:00-20:00',
  '20:00-22:00',
  '22:00-24:00',
];

const formData = ref<SystemMeetingBookingApi.MeetingBooking>();
const roomOptions = ref<Array<{ label: string; value: number }>>([]);
const userOptions = ref<Array<{ label: string; value: number }>>([]);
const mode = ref<Mode>('admin');

const getTitle = computed(() => {
  return formData.value?.id
    ? $t('ui.actionTitle.edit', ['会议室预定'])
    : $t('ui.actionTitle.create', ['会议室预定']);
});

function splitBookingTime(
  booking?: Partial<SystemMeetingBookingApi.MeetingBooking>,
): MeetingBookingFormValues {
  if (!booking?.startTime || !booking?.endTime) {
    return {
      ...booking,
      bookingDate: undefined,
      timeSlot: undefined,
    };
  }
  return {
    ...booking,
    bookingDate: dayjs(booking.startTime).format('YYYY-MM-DD'),
    timeSlot: `${dayjs(booking.startTime).format('HH:mm')}-${dayjs(booking.endTime).format('HH:mm')}`,
  };
}

function buildBookingPayload(values: MeetingBookingFormValues) {
  const [startPart, endPart] = (values.timeSlot || '').split('-');
  const bookingDate = values.bookingDate;
  return {
    ...values,
    startTime:
      bookingDate && startPart ? `${bookingDate} ${startPart}:00` : undefined,
    endTime: bookingDate && endPart ? `${bookingDate} ${endPart}:00` : undefined,
  } as SystemMeetingBookingApi.MeetingBooking;
}

function normalizeEndHour(timeSlot?: string) {
  const endPart = timeSlot?.split('-')?.[1];
  if (!endPart) {
    return undefined;
  }
  if (endPart === '24:00') {
    return 24;
  }
  return Number(endPart.split(':')[0]);
}

function getAvailableTimeSlotOptions(bookingDate?: string) {
  const today = dayjs().format('YYYY-MM-DD');
  const now = dayjs();
  return ALL_TIME_SLOTS.filter((slot) => {
    if (!bookingDate) {
      return true;
    }
    if (bookingDate > today) {
      return true;
    }
    if (bookingDate < today) {
      return false;
    }
    const endHour = normalizeEndHour(slot);
    if (endHour === undefined) {
      return false;
    }
    const slotEnd = endHour === 24
      ? dayjs(`${bookingDate} 23:59:59`)
      : dayjs(`${bookingDate} ${String(endHour).padStart(2, '0')}:00:00`);
    return slotEnd.isAfter(now);
  }).map((slot) => ({
    label: slot,
    value: slot,
  }));
}

function normalizeCreateValues(data?: ModalData): MeetingBookingFormValues {
  const bookingDate = data?.initialValues?.bookingDate || dayjs().format('YYYY-MM-DD');
  const timeSlotOptions = getAvailableTimeSlotOptions(bookingDate);
  const timeSlot = data?.initialValues?.timeSlot;
  return {
    ...data?.initialValues,
    bookingDate,
    timeSlot: timeSlotOptions.some((item) => item.value === timeSlot)
      ? timeSlot
      : undefined,
  };
}

async function syncTimeSlotOptions(bookingDate?: string, selectedTimeSlot?: string) {
  const options = getAvailableTimeSlotOptions(bookingDate);
  const nextSchema = useBookingFormSchema(roomOptions.value, userOptions.value, {
    bookingDate,
    timeSlotOptions: options,
  });
  formApi.setState({ schema: nextSchema });
  if (selectedTimeSlot && !options.some((item) => item.value === selectedTimeSlot)) {
    await formApi.setValues({ timeSlot: undefined });
  }
}

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: {
      class: 'w-full',
    },
    formItemClass: 'col-span-2',
    labelWidth: 90,
  },
  layout: 'horizontal',
  schema: [],
  showDefaultActions: false,
  handleValuesChange: async (values, fieldsChanged) => {
    if (!fieldsChanged.includes('bookingDate')) {
      return;
    }
    const nextBookingDate = values.bookingDate as string | undefined;
    const currentTimeSlot = values.timeSlot as string | undefined;
    await syncTimeSlotOptions(nextBookingDate, currentTimeSlot);
  },
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) {
      return;
    }
    modalApi.lock();
    try {
      const data = (await formApi.getValues()) as MeetingBookingFormValues;
      const payload = {
        ...buildBookingPayload(data),
        forceConflict: false,
      };
      if (!payload.startTime || !payload.endTime || !dayjs(payload.endTime).isAfter(dayjs())) {
        message.warning('请选择未结束的有效两小时时段');
        return;
      }
      const conflicts = await checkMeetingBookingConflict(payload);
      if (conflicts.length > 0) {
        const confirmed = await new Promise<boolean>((resolve) => {
          AntModal.confirm({
            title: '检测到冲突预定',
            content: conflicts
              .map(
                (item) =>
                  `${item.meetingRoomName || ''} ${item.startTime} - ${item.endTime} ${item.subject}`,
              )
              .join('\n'),
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          });
        });
        if (!confirmed) {
          return;
        }
        payload.forceConflict = true;
      }
      if (formData.value?.id) {
        await (mode.value === 'mine'
          ? updateMyMeetingBooking(payload)
          : updateMeetingBooking(payload));
      } else {
        await createMeetingBooking(payload);
      }
      await modalApi.close();
      emit('success');
      message.success($t('ui.actionMessage.operationSuccess'));
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      formData.value = undefined;
      return;
    }
    const data = modalApi.getData<ModalData>();
    roomOptions.value = (data?.roomOptions || []).map((item) => ({
      label: `${item.name}${item.location ? ` (${item.location})` : ''}`,
      value: item.id,
    }));
    userOptions.value = (data?.userOptions || []).map((item) => ({
      label: item.nickname,
      value: item.id!,
    }));
    mode.value = data?.mode || 'admin';
    const createValues = normalizeCreateValues(data);
    await syncTimeSlotOptions(createValues.bookingDate, createValues.timeSlot);
    if (!data?.booking?.id) {
      formData.value = undefined;
      await formApi.setValues(createValues);
      return;
    }
    modalApi.lock();
    try {
      formData.value = await getMeetingBooking(data.booking.id);
      const values = splitBookingTime(formData.value);
      await syncTimeSlotOptions(values.bookingDate, values.timeSlot);
      await formApi.setValues(values);
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal class="w-[720px]" :title="getTitle">
    <Form class="mx-4" />
  </Modal>
</template>
