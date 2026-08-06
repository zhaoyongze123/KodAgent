function normalizeBasePath(basePath: string) {
  if (!basePath || basePath === '/') {
    return '';
  }
  return basePath.endsWith('/') ? basePath.slice(0, -1) : basePath;
}

function buildCurrentOrigin() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return '';
  }
  return window.location.origin;
}

function rewriteKnownPath(pathname: string, search: string, hash: string) {
  const currentOrigin = buildCurrentOrigin();
  const basePath = normalizeBasePath(import.meta.env.VITE_BASE || '/');
  if (!currentOrigin) {
    return `${pathname}${search}${hash}`;
  }
  if (pathname.startsWith('/admin-api/')) {
    return `${currentOrigin}${pathname}${search}${hash}`;
  }
  if (pathname.startsWith('/static/')) {
    return `${currentOrigin}${basePath}${pathname}${search}${hash}`;
  }
  if (pathname.startsWith('/oa/')) {
    return `${currentOrigin}${pathname}${search}${hash}`;
  }
  return `${pathname}${search}${hash}`;
}

function shouldRewriteOrigin(url: URL) {
  if (typeof window === 'undefined') {
    return false;
  }
  if (url.origin === window.location.origin) {
    return false;
  }
  return (
    url.pathname.startsWith('/admin-api/') ||
    url.pathname.startsWith('/static/') ||
    url.hostname === '127.0.0.1' ||
    url.hostname === 'localhost'
  );
}

const OFFICE_PREVIEW_EXTENSIONS = new Set([
  'DOC',
  'DOCX',
  'XLS',
  'XLSX',
  'PPT',
  'PPTX',
]);

function getFileExtension(fileName?: string) {
  const normalized = (fileName || '').split(/[?#]/, 1)[0] || '';
  const lastPart = normalized.slice(normalized.lastIndexOf('/') + 1);
  const extension = lastPart.includes('.')
    ? lastPart.slice(lastPart.lastIndexOf('.') + 1)
    : '';
  return extension.toUpperCase();
}

export function normalizeOaAssetUrl(rawUrl?: null | string) {
  const value = (rawUrl || '').trim();
  if (!value) {
    return '';
  }
  if (
    value.startsWith('data:') ||
    value.startsWith('blob:') ||
    value.startsWith('javascript:')
  ) {
    return value;
  }
  if (value.startsWith('/')) {
    return rewriteKnownPath(value, '', '');
  }
  if (value.startsWith('static/')) {
    return rewriteKnownPath(`/${value}`, '', '');
  }
  if (value.startsWith('admin-api/')) {
    return rewriteKnownPath(`/${value}`, '', '');
  }
  try {
    const currentOrigin = buildCurrentOrigin() || 'http://localhost';
    const parsedUrl = new URL(value, currentOrigin);
    if (shouldRewriteOrigin(parsedUrl)) {
      return rewriteKnownPath(
        parsedUrl.pathname,
        parsedUrl.search,
        parsedUrl.hash,
      );
    }
    return parsedUrl.toString();
  } catch {
    return value;
  }
}

/**
 * Build an offline preview URL for office documents.
 *
 * The preview service must fetch the file URL itself, so the backend file
 * endpoint is intentionally kept as the Base64-encoded `url` query parameter.
 * KKFileView 4.1.0 decodes this parameter before fetching it. The backend
 * marks that endpoint as public (`/infra/file/{configId}/get/**`), which lets
 * KKFileView fetch it without a browser login cookie.
 */
export function getOaFilePreviewUrl(fileUrl: string, fileName?: string) {
  const normalizedFileUrl = (fileUrl || '').trim();
  const previewEndpoint = (import.meta.env.VITE_FILE_PREVIEW_URL || '').trim();
  if (
    !normalizedFileUrl ||
    !previewEndpoint ||
    !OFFICE_PREVIEW_EXTENSIONS.has(getFileExtension(fileName))
  ) {
    return normalizedFileUrl;
  }
  try {
    const baseUrl =
      typeof window === 'undefined' ? 'http://localhost/' : window.location.origin;
    const previewUrl = new URL(previewEndpoint, baseUrl);
    const bytes = new TextEncoder().encode(normalizedFileUrl);
    let binary = '';
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    previewUrl.searchParams.set('url', btoa(binary));
    return previewUrl.toString();
  } catch {
    return normalizedFileUrl;
  }
}
