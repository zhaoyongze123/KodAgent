import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';

import { DICT_TYPE } from '@vben/constants';
import { getDictOptions } from '@vben/hooks';

export function useBookingFormSchema(
  roomOptions: Array<{ label: string; value: number }>,
  userOptions: Array<{ label: string; value: number }>,
  options?: {
    bookingDate?: string;
    timeSlotOptions?: Array<{ label: string; value: string }>;
  },
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
      fieldName: 'subject',
      label: '会议主题',
      component: 'Input',
      componentProps: {
        placeholder: '请输入会议主题',
      },
      rules: 'required',
    },
    {
      fieldName: 'meetingRoomId',
      label: '会议室',
      component: 'Select',
      componentProps: {
        options: roomOptions,
        placeholder: '请选择会议室',
      },
      rules: 'required',
    },
    {
      fieldName: 'bookingDate',
      label: '预定日期',
      component: 'DatePicker',
      componentProps: {
        valueFormat: 'YYYY-MM-DD',
        format: 'YYYY-MM-DD',
        disabledDate: (current: any) =>
          current ? current.startOf('day').valueOf() < Date.now() - 24 * 60 * 60 * 1000 : false,
      },
      rules: 'required',
    },
    {
      fieldName: 'timeSlot',
      label: '时间段',
      component: 'Select',
      componentProps: {
        options: options?.timeSlotOptions || [],
        placeholder: '请选择固定两小时时段',
      },
      rules: 'required',
    },
    {
      fieldName: 'startTime',
      label: '开始时间',
      component: 'Input',
      dependencies: {
        triggerFields: [''],
        show: () => false,
      },
    },
    {
      fieldName: 'endTime',
      label: '结束时间',
      component: 'Input',
      dependencies: {
        triggerFields: [''],
        show: () => false,
      },
    },
    {
      fieldName: 'attendeeUserIds',
      label: '参会人员',
      component: 'Select',
      componentProps: {
        mode: 'multiple',
        options: userOptions,
        placeholder: '请选择参会人员',
      },
    },
    {
      fieldName: 'remark',
      label: '备注',
      component: 'Textarea',
      componentProps: {
        rows: 3,
        placeholder: '请输入备注',
      },
    },
  ];
}

export function useBookingGridFormSchema(
  roomOptions: Array<{ label: string; value: number }>,
  userOptions: Array<{ label: string; value: number }>,
): VbenFormSchema[] {
  return [
    {
      fieldName: 'meetingRoomId',
      label: '会议室',
      component: 'Select',
      componentProps: {
        options: roomOptions,
        placeholder: '请选择会议室',
        allowClear: true,
      },
    },
    {
      fieldName: 'applicantUserId',
      label: '申请人',
      component: 'Select',
      componentProps: {
        options: userOptions,
        placeholder: '请选择申请人',
        allowClear: true,
      },
    },
    {
      fieldName: 'subject',
      label: '会议主题',
      component: 'Input',
      componentProps: {
        placeholder: '请输入会议主题',
        allowClear: true,
      },
    },
    {
      fieldName: 'status',
      label: '状态',
      component: 'Select',
      componentProps: {
        options: getDictOptions(
          DICT_TYPE.SYSTEM_MEETING_BOOKING_STATUS,
          'number',
        ),
        placeholder: '请选择状态',
        allowClear: true,
      },
    },
  ];
}

export function useBookingGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'id',
      title: '编号',
      minWidth: 90,
    },
    {
      field: 'subject',
      title: '会议主题',
      minWidth: 180,
    },
    {
      field: 'meetingRoomName',
      title: '会议室',
      minWidth: 160,
    },
    {
      field: 'startTime',
      title: '开始时间',
      minWidth: 180,
      formatter: 'formatDateTime',
    },
    {
      field: 'endTime',
      title: '结束时间',
      minWidth: 180,
      formatter: 'formatDateTime',
    },
    {
      field: 'applicantUserNickname',
      title: '申请人',
      minWidth: 120,
    },
    {
      field: 'status',
      title: '状态',
      minWidth: 100,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.SYSTEM_MEETING_BOOKING_STATUS },
      },
    },
    {
      field: 'createTime',
      title: '创建时间',
      minWidth: 180,
      formatter: 'formatDateTime',
    },
    {
      title: '操作',
      width: 220,
      fixed: 'right',
      slots: { default: 'actions' },
    },
  ];
}
