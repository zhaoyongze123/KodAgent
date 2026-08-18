import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace SystemMeetingBookingApi {
  export interface MeetingBooking {
    id?: number;
    subject: string;
    meetingRoomId: number;
    meetingRoomName?: string;
    startTime: string;
    endTime: string;
    applicantUserId?: number;
    applicantUserNickname?: string;
    attendeeUserIds?: number[];
    attendeeUserNicknames?: string[];
    remark?: string;
    status?: number;
    forceConflict: boolean;
    cancelReason?: string;
    cancelType?: number;
    createTime?: Date;
  }

  export interface ConflictItem {
    id: number;
    subject: string;
    meetingRoomId: number;
    meetingRoomName?: string;
    applicantUserId?: number;
    applicantUserNickname?: string;
    startTime: string;
    endTime: string;
  }
}

export function getMeetingBookingPage(params: PageParam) {
  return requestClient.get<PageResult<SystemMeetingBookingApi.MeetingBooking>>(
    '/system/meeting-booking/page',
    { params },
  );
}

export function getMyMeetingBookingPage(params: PageParam) {
  return requestClient.get<PageResult<SystemMeetingBookingApi.MeetingBooking>>(
    '/system/meeting-booking/my-page',
    { params },
  );
}

export function getMeetingBooking(id: number) {
  return requestClient.get<SystemMeetingBookingApi.MeetingBooking>(
    `/system/meeting-booking/get?id=${id}`,
  );
}

export function createMeetingBooking(
  data: SystemMeetingBookingApi.MeetingBooking,
) {
  return requestClient.post('/system/meeting-booking/create', data);
}

export function updateMeetingBooking(
  data: SystemMeetingBookingApi.MeetingBooking,
) {
  return requestClient.put('/system/meeting-booking/update', data);
}

export function updateMyMeetingBooking(
  data: SystemMeetingBookingApi.MeetingBooking,
) {
  return requestClient.put('/system/meeting-booking/update-my', data);
}

export function cancelMyMeetingBooking(id: number, cancelReason?: string) {
  return requestClient.put('/system/meeting-booking/cancel-my', {
    id,
    cancelReason,
  });
}

export function deleteMeetingBooking(id: number, cancelReason?: string) {
  return requestClient.delete('/system/meeting-booking/delete', {
    params: { id, cancelReason },
  });
}

export function checkMeetingBookingConflict(
  data: Partial<SystemMeetingBookingApi.MeetingBooking>,
) {
  return requestClient.post<SystemMeetingBookingApi.ConflictItem[]>(
    '/system/meeting-booking/check-conflict',
    data,
  );
}

export function getWeekSchedule(params: any) {
  return requestClient.get<SystemMeetingBookingApi.MeetingBooking[]>(
    '/system/meeting-booking/schedule/week',
    { params },
  );
}

export function getMonthSchedule(params: any) {
  return requestClient.get<SystemMeetingBookingApi.MeetingBooking[]>(
    '/system/meeting-booking/schedule/month',
    { params },
  );
}
