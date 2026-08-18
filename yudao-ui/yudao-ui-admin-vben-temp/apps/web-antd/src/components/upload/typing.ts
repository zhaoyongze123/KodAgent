import type { AxiosResponse } from '@vben/request';
import type { UploadFile } from 'ant-design-vue';

import type { AxiosProgressEvent } from '#/api/infra/file';

export enum UploadResultStatus {
  DONE = 'done',
  ERROR = 'error',
  SUCCESS = 'success',
  UPLOADING = 'uploading',
}

export type UploadListType = 'picture' | 'picture-card' | 'text';

export interface FileUploadExtraAction {
  key: string;
  label: string;
  onClick: () => void | Promise<void>;
  disabled?: boolean | (() => boolean);
  show?: boolean | (() => boolean);
}

export interface FileUploadProps {
  accept?: string[]; // 根据后缀，或者其他
  api?: (
    file: File,
    onUploadProgress?: AxiosProgressEvent,
  ) => Promise<AxiosResponse | Record<string, any>>;
  directory?: string; // 上传的目录
  disabled?: boolean | (() => boolean);
  drag?: boolean; // 是否支持拖拽上传
  helpText?: string;
  listType?: UploadListType;
  maxNumber?: number; // 最大数量的文件，Infinity不限制
  modelValue?: Record<string, any> | Record<string, any>[] | string | string[]; // v-model 支持
  maxSize?: number; // 文件最大多少MB
  multiple?: boolean; // 是否支持多选
  extraActions?: FileUploadExtraAction[]; // 额外操作按钮
  previewUrlResolver?: (file: UploadFile) => string | Promise<string>;
  resultField?: string; // support xxx.xxx.xx
  showDescription?: boolean; // 是否显示下面的描述
  uploadText?: string; // 上传按钮文案
  value?: Record<string, any> | Record<string, any>[] | string | string[];
}
