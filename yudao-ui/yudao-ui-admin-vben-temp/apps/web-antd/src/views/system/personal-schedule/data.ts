import type { VbenFormSchema } from '#/adapter/form';
import type { SystemPersonalScheduleApi } from '#/api/system/personal-schedule';

import dayjs from 'dayjs';

export interface PersonalScheduleFormValues
  extends Partial<SystemPersonalScheduleApi.PersonalSchedule> {}

export function usePersonalScheduleFormSchema(
  userOptions: Array<{ label: string; value: number }>,
): VbenFormSchema[] {
  return [
    {
      fieldName: 'id',
      component: 'Input',
      dependencies: {
        triggerFields: [''],
        show: () => false,
      },
    },
    {
      fieldName: 'title',
      label: '日程标题',
      component: 'Input',
      componentProps: {
        placeholder: '请输入日程标题',
      },
      rules: 'required',
    },
    {
      fieldName: 'startTime',
      label: '开始时间',
      component: 'DatePicker',
      componentProps: {
        showTime: true,
        valueFormat: 'YYYY-MM-DD HH:mm:ss',
        format: 'YYYY-MM-DD HH:mm',
      },
      rules: 'required',
    },
    {
      fieldName: 'endTime',
      label: '结束时间',
      component: 'DatePicker',
      componentProps: {
        showTime: true,
        valueFormat: 'YYYY-MM-DD HH:mm:ss',
        format: 'YYYY-MM-DD HH:mm',
      },
      rules: 'required',
    },
    {
      fieldName: 'location',
      label: '地址',
      component: 'Input',
      componentProps: {
        placeholder: '请输入地址，可不填',
      },
    },
    {
      fieldName: 'attendeeUserIds',
      label: '参与者',
      component: 'Select',
      componentProps: {
        mode: 'multiple',
        options: userOptions,
        placeholder: '请选择内部参与者',
      },
    },
    {
      fieldName: 'otherParticipants',
      label: '外部参与者',
      component: 'Input',
      componentProps: {
        placeholder: '请输入外部参与者，可不填',
      },
    },
    {
      fieldName: 'description',
      label: '文字描述',
      component: 'Textarea',
      componentProps: {
        rows: 4,
        placeholder: '请输入日程描述',
      },
    },
  ];
}

export function normalizeSchedulePayload(
  values: PersonalScheduleFormValues,
): SystemPersonalScheduleApi.PersonalSchedule {
  return {
    ...values,
    startTime: values.startTime
      ? dayjs(values.startTime).format('YYYY-MM-DD HH:mm:ss')
      : '',
    endTime: values.endTime
      ? dayjs(values.endTime).format('YYYY-MM-DD HH:mm:ss')
      : '',
  } as SystemPersonalScheduleApi.PersonalSchedule;
}

export function buildCalendarEventTitle(
  event: SystemPersonalScheduleApi.CalendarEvent,
) {
  const timeRange = `${dayjs(event.startTime).format('HH:mm')}-${dayjs(event.endTime).format('HH:mm')}`;
  const title = [timeRange, event.title].filter(Boolean).join(' ');
  const location = event.location ? `（${event.location}）` : '';
  const participants = (event.attendeeUserNicknames || []).join('、');
  const participantText = participants ? ` [${participants}]` : '';
  return `${title}${location}${participantText}`;
}

export function buildCalendarEventTooltip(
  event: SystemPersonalScheduleApi.CalendarEvent,
) {
  return [
    `时间：${dayjs(event.startTime).format('YYYY-MM-DD HH:mm')} - ${dayjs(event.endTime).format('YYYY-MM-DD HH:mm')}`,
    `标题：${event.title}`,
    event.location ? `地址：${event.location}` : '',
    event.attendeeUserNicknames?.length
      ? `参与者：${event.attendeeUserNicknames.join('、')}`
      : '',
    event.otherParticipants ? `外部参与者：${event.otherParticipants}` : '',
    event.description ? `说明：${event.description}` : '',
  ]
    .filter(Boolean)
    .join('\n');
}
