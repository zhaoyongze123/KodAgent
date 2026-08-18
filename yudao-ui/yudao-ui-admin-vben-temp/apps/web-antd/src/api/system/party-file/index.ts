import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace SystemPartyFileApi {
  export interface PartyFileCategory {
    id?: number;
    name: string;
    parentId: number;
    sort: number;
    status: number;
    createTime?: Date;
    children?: PartyFileCategory[];
  }

  export interface PartyFileTarget {
    targetType: number;
    targetId?: number;
    targetName?: string;
  }

  export interface PartyFileKodSource {
    id?: number;
    name: string;
    baseUrl: string;
    appName: string;
    accessToken?: string;
    serviceUsername?: string;
    servicePassword?: string;
    hasServicePassword?: boolean;
    tokenExpireTime?: Date | string;
    rootFolderPath: string;
    rootFolderName: string;
    status: number;
    isDefault?: boolean;
    createTime?: Date | string;
  }

  export interface PartyFileKodFolder {
    key: string;
    title: string;
    value: string;
    path: string;
    isLeaf?: boolean;
    children?: PartyFileKodFolder[];
  }

  export interface PartyFileAttachment {
    id: number;
    name: string;
    url?: string;
    size?: number;
    type?: string;
  }

  export interface PartyFileKodFile {
    name: string;
    path: string;
    pathDisplay?: string;
    size?: number;
    type?: string;
  }

  export interface PartyFileReadRecord {
    userId: number;
    userNickname: string;
    deptId?: number;
    deptName?: string;
    readTime?: Date | string;
    readSource?: number;
  }

  export interface PartyFileUnreadRecord {
    userId: number;
    userNickname: string;
    deptId?: number;
    deptName?: string;
  }

  export interface PartyFile {
    id?: number;
    title: string;
    categoryId: number;
    categoryName?: string;
    summary?: string;
    content?: string;
    attachmentFileIds?: string;
    storageType: number;
    kodSourceId?: number;
    kodFolderPath?: string;
    kodFolderName?: string;
    status: number;
    publishTime: Date | string;
    creator?: string;
    createTime?: Date | string;
    readStatus?: boolean;
    readCount?: number;
    unreadCount?: number;
    attachments?: PartyFileAttachment[];
    targets: PartyFileTarget[];
    readList?: PartyFileReadRecord[];
    unreadList?: PartyFileUnreadRecord[];
  }
}

export function getPartyFileCategoryList(params?: { status?: number }) {
  return requestClient.get<SystemPartyFileApi.PartyFileCategory[]>(
    '/system/party-file-category/list',
    { params },
  );
}

export function getSimplePartyFileCategoryList() {
  return requestClient.get<SystemPartyFileApi.PartyFileCategory[]>(
    '/system/party-file-category/simple-list',
  );
}

export function getPartyFileCategory(id: number) {
  return requestClient.get<SystemPartyFileApi.PartyFileCategory>(
    `/system/party-file-category/get?id=${id}`,
  );
}

export function createPartyFileCategory(
  data: SystemPartyFileApi.PartyFileCategory,
) {
  return requestClient.post('/system/party-file-category/create', data);
}

export function updatePartyFileCategory(
  data: SystemPartyFileApi.PartyFileCategory,
) {
  return requestClient.put('/system/party-file-category/update', data);
}

export function deletePartyFileCategory(id: number) {
  return requestClient.delete(`/system/party-file-category/delete?id=${id}`);
}

export function getPartyFilePage(params: PageParam) {
  return requestClient.get<PageResult<SystemPartyFileApi.PartyFile>>(
    '/system/party-file/page',
    { params },
  );
}

export function getPartyFile(id: number) {
  return requestClient.get<SystemPartyFileApi.PartyFile>(
    `/system/party-file/get?id=${id}`,
  );
}

export function createPartyFile(data: SystemPartyFileApi.PartyFile) {
  return requestClient.post('/system/party-file/create', data);
}

export function updatePartyFile(data: SystemPartyFileApi.PartyFile) {
  return requestClient.put('/system/party-file/update', data);
}

export function deletePartyFile(id: number) {
  return requestClient.delete(`/system/party-file/delete?id=${id}`);
}

export function getMyPartyFilePage(params: PageParam) {
  return requestClient.get<PageResult<SystemPartyFileApi.PartyFile>>(
    '/system/party-file/my-page',
    { params },
  );
}

export function getMyPartyFile(id: number) {
  return requestClient.get<SystemPartyFileApi.PartyFile>(
    `/system/party-file/my-get?id=${id}`,
  );
}

export function getMyPartyFileAttachment(
  id: number,
  fileId: number,
  action: 'download' | 'preview' = 'download',
) {
  return requestClient.get<SystemPartyFileApi.PartyFile>(
    `/system/party-file/my-attachment?id=${id}&fileId=${fileId}&action=${action}`,
  );
}

export function uploadPartyFileAttachment(data: {
  file: File;
  storageType: number;
  kodSourceId?: number;
  kodFolderPath?: string;
}) {
  return requestClient.upload<SystemPartyFileApi.PartyFileAttachment>(
    '/system/party-file/attachment/upload',
    data,
  );
}

export function getPartyFileKodFiles(params: {
  kodSourceId: number;
  kodFolderPath: string;
}) {
  return requestClient.post<SystemPartyFileApi.PartyFileKodFile[]>(
    '/system/party-file/attachment/kod-files',
    params,
  );
}

export function selectPartyFileKodFiles(data: {
  kodSourceId: number;
  kodFolderPath: string;
  files: SystemPartyFileApi.PartyFileKodFile[];
}) {
  return requestClient.post<SystemPartyFileApi.PartyFileAttachment[]>(
    '/system/party-file/attachment/kod-select',
    data,
  );
}

export function getCurrentUserPartyFileKodFolderTree() {
  return requestClient.get<SystemPartyFileApi.PartyFileKodFolder[]>(
    '/system/party-file/attachment/kod-user-folder-tree',
  );
}

export function getCurrentUserPartyFileKodFolderChildren(params: {
  kodFolderPath: string;
}) {
  return requestClient.get<SystemPartyFileApi.PartyFileKodFolder[]>(
    '/system/party-file/attachment/kod-user-folder-children',
    { params },
  );
}

export function getCurrentUserPartyFileKodFiles(params: {
  kodFolderPath: string;
}) {
  return requestClient.post<SystemPartyFileApi.PartyFileKodFile[]>(
    '/system/party-file/attachment/kod-user-files',
    params,
  );
}

export function selectCurrentUserPartyFileKodFiles(data: {
  kodFolderPath: string;
  files: SystemPartyFileApi.PartyFileKodFile[];
}) {
  return requestClient.post<SystemPartyFileApi.PartyFileAttachment[]>(
    '/system/party-file/attachment/kod-user-select',
    data,
  );
}

export function getPartyFileAttachmentAccessUrl(fileId: number) {
  return `/admin-api/system/party-file/attachment/access?fileId=${fileId}`;
}

export function getPartyFileKodSourcePage(params: PageParam & { name?: string; status?: number }) {
  return requestClient.get<PageResult<SystemPartyFileApi.PartyFileKodSource>>(
    '/system/party-file-kod-source/page',
    { params },
  );
}

export function getPartyFileKodSource(id: number) {
  return requestClient.get<SystemPartyFileApi.PartyFileKodSource>(
    `/system/party-file-kod-source/get?id=${id}`,
  );
}

export function createPartyFileKodSource(data: SystemPartyFileApi.PartyFileKodSource) {
  return requestClient.post('/system/party-file-kod-source/create', data);
}

export function updatePartyFileKodSource(data: SystemPartyFileApi.PartyFileKodSource) {
  return requestClient.put('/system/party-file-kod-source/update', data);
}

export function deletePartyFileKodSource(id: number) {
  return requestClient.delete(`/system/party-file-kod-source/delete?id=${id}`);
}

export function getSimplePartyFileKodSourceList() {
  return requestClient.get<SystemPartyFileApi.PartyFileKodSource[]>(
    '/system/party-file-kod-source/simple-list',
  );
}

export function getPartyFileKodFolderTree(id: number) {
  return requestClient.get<SystemPartyFileApi.PartyFileKodFolder[]>(
    `/system/party-file-kod-source/folder-tree?id=${id}`,
  );
}

export function downloadPartyFileAttachment(id: number, fileId: number) {
  return requestClient.download('/system/party-file/attachment/download', {
    params: { id, fileId },
  });
}

export function downloadMyPartyFileAttachment(id: number, fileId: number) {
  return requestClient.download('/system/party-file/my-attachment/download', {
    params: { id, fileId },
  });
}

export function previewPartyFileAttachment(id: number, fileId: number) {
  return requestClient.download('/system/party-file/attachment/preview', {
    params: { id, fileId },
  });
}

export function previewMyPartyFileAttachment(id: number, fileId: number) {
  return requestClient.download('/system/party-file/my-attachment/preview', {
    params: { id, fileId },
  });
}

export function getPartyFileAttachmentPreviewUrl(id: number, fileId: number) {
  return requestClient.get<string>('/system/party-file/attachment/preview-url', {
    params: { id, fileId },
  });
}

export function getMyPartyFileAttachmentPreviewUrl(id: number, fileId: number) {
  return requestClient.get<string>('/system/party-file/my-attachment/preview-url', {
    params: { id, fileId },
  });
}

export function getPartyFileAttachmentPreviewUrlByFileId(fileId: number) {
  return requestClient.get<string>('/system/party-file/attachment/preview-url-by-file', {
    params: { fileId },
  });
}
