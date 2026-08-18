import type { SystemMeetingBookingApi } from '#/api/system/meeting-booking';
import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace SystemPersonalScheduleApi {
  export interface PersonalSchedule {
    id?: number;
    title: string;
    startTime: string;
    endTime: string;
    location?: string;
    description?: string;
    attendeeUserIds?: number[];
    attendeeUserNicknames?: string[];
    otherParticipants?: string;
    ownerUserId?: number;
    createTime?: string;
  }

  export type CalendarEventSourceType = 'MEETING_BOOKING' | 'PERSONAL_SCHEDULE';

  export interface CalendarEvent {
    sourceType: CalendarEventSourceType;
    sourceId: number;
    editable: boolean;
    title: string;
    startTime: string;
    endTime: string;
    location?: string;
    description?: string;
    attendeeUserIds?: number[];
    attendeeUserNicknames?: string[];
    otherParticipants?: string;
    meetingRoomId?: number;
    meetingRoomName?: string;
  }
}

export function getPersonalSchedule(id: number) {
  return requestClient.get<SystemPersonalScheduleApi.PersonalSchedule>(
    `/system/personal-schedule/get?id=${id}`,
  );
}

export function createPersonalSchedule(
  data: SystemPersonalScheduleApi.PersonalSchedule,
) {
  return requestClient.post('/system/personal-schedule/create', data);
}

export function updatePersonalSchedule(
  data: SystemPersonalScheduleApi.PersonalSchedule,
) {
  return requestClient.put('/system/personal-schedule/update', data);
}

export function deletePersonalSchedule(id: number) {
  return requestClient.delete('/system/personal-schedule/delete', {
    params: { id },
  });
}

export function getMyPersonalCalendar(params: PageParam) {
  return requestClient.get<SystemPersonalScheduleApi.CalendarEvent[]>(
    '/system/personal-schedule/my-calendar',
    { params },
  );
}

export function isMeetingBookingEvent(
  event: SystemPersonalScheduleApi.CalendarEvent,
): event is SystemPersonalScheduleApi.CalendarEvent &
  Pick<SystemMeetingBookingApi.MeetingBooking, 'meetingRoomId' | 'meetingRoomName'> {
  return event.sourceType === 'MEETING_BOOKING';
}
