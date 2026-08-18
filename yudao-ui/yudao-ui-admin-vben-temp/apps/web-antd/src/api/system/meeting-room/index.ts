import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace SystemMeetingRoomApi {
  export interface MeetingRoom {
    id?: number;
    name: string;
    location: string;
    capacity: number;
    equipment?: string;
    remark?: string;
    status: number;
    sort: number;
    createTime?: Date;
  }

  export interface MeetingRoomSimple {
    id: number;
    name: string;
    location?: string;
  }
}

export function getMeetingRoomPage(params: PageParam) {
  return requestClient.get<PageResult<SystemMeetingRoomApi.MeetingRoom>>(
    '/system/meeting-room/page',
    { params },
  );
}

export function getMeetingRoom(id: number) {
  return requestClient.get<SystemMeetingRoomApi.MeetingRoom>(
    `/system/meeting-room/get?id=${id}`,
  );
}

export function createMeetingRoom(data: SystemMeetingRoomApi.MeetingRoom) {
  return requestClient.post('/system/meeting-room/create', data);
}

export function updateMeetingRoom(data: SystemMeetingRoomApi.MeetingRoom) {
  return requestClient.put('/system/meeting-room/update', data);
}

export function deleteMeetingRoom(id: number) {
  return requestClient.delete(`/system/meeting-room/delete?id=${id}`);
}

export function getSimpleMeetingRoomList() {
  return requestClient.get<SystemMeetingRoomApi.MeetingRoomSimple[]>(
    '/system/meeting-room/simple-list',
  );
}
