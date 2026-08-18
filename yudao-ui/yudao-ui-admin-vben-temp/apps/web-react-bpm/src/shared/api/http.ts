const API_PREFIX = '/admin-api';

export interface PageParams {
  pageNo?: number;
  pageSize?: number;
  [key: string]: unknown;
}

export interface PageResult<T> {
  list: T[];
  total: number;
}

type RequestBody = BodyInit | FormData | object;

interface HttpOptions extends Omit<RequestInit, 'body'> {
  body?: RequestBody;
  params?: Record<string, unknown>;
}

function buildHeaders(body: RequestBody | undefined, headers?: HeadersInit) {
  const token = localStorage.getItem('approval_access_token');
  const tenantId = localStorage.getItem('approval_tenant_id');
  const visitTenantId = localStorage.getItem('approval_visit_tenant_id');

  return {
    ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(tenantId ? { 'tenant-id': tenantId } : {}),
    ...(visitTenantId ? { 'visit-tenant-id': visitTenantId } : {}),
    ...headers,
  };
}

function buildQuery(params?: Record<string, unknown>) {
  if (!params) {
    return '';
  }
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    searchParams.set(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `?${query}` : '';
}

async function request<T>(path: string, options: HttpOptions = {}) {
  const { params, headers, body, ...rest } = options;
  const requestBody =
    body && !(body instanceof FormData) && typeof body !== 'string'
      ? JSON.stringify(body)
      : body;
  const response = await fetch(`${API_PREFIX}${path}${buildQuery(params)}`, {
    ...rest,
    headers: buildHeaders(body, headers),
    body: requestBody,
  });

  if (!response.ok) {
    let errorMessage = `请求失败：${response.status}`;
    try {
      const errorResult = await response.json();
      if (errorResult?.msg) {
        errorMessage = String(errorResult.msg);
      }
    } catch {
      // 非 JSON 错误体时保留默认文案
    }
    throw new Error(errorMessage);
  }

  const result = await response.json();
  if (result.code !== 0) {
    throw new Error(result.msg || '接口返回失败');
  }
  return result.data as T;
}

async function requestBlob(path: string, options: HttpOptions = {}) {
  const { params, headers, body, ...rest } = options;
  const requestBody =
    body && !(body instanceof FormData) && typeof body !== 'string'
      ? JSON.stringify(body)
      : body;
  const response = await fetch(`${API_PREFIX}${path}${buildQuery(params)}`, {
    ...rest,
    headers: buildHeaders(body, headers),
    body: requestBody,
  });

  if (!response.ok) {
    let errorMessage = `请求失败：${response.status}`;
    try {
      const errorResult = await response.json();
      if (errorResult?.msg) {
        errorMessage = String(errorResult.msg);
      }
    } catch {
      // 非 JSON 错误体时保留默认文案
    }
    throw new Error(errorMessage);
  }

  return response.blob();
}

export const http = {
  delete: <T>(path: string, options?: HttpOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
  download: (path: string, options?: HttpOptions) =>
    requestBlob(path, { ...options, method: 'GET' }),
  get: <T>(path: string, options?: HttpOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: RequestBody, options?: HttpOptions) =>
    request<T>(path, { ...options, body, method: 'POST' }),
  put: <T>(path: string, body?: RequestBody, options?: HttpOptions) =>
    request<T>(path, { ...options, body, method: 'PUT' }),
  upload: <T>(
    path: string,
    payload: Record<string, FormDataEntryValue | FormDataEntryValue[] | undefined>,
    options?: Omit<HttpOptions, 'body'>,
  ) => {
    const formData = new FormData();
    Object.entries(payload).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      if (Array.isArray(value)) {
        value.forEach((item) => formData.append(key, item));
        return;
      }
      formData.append(key, value);
    });
    return request<T>(path, { ...options, body: formData, method: 'POST' });
  },
};
