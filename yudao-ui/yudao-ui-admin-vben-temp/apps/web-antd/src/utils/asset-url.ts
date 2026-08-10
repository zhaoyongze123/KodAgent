import { useAppConfig } from '@vben/hooks';

const { filePreviewFetchOrigin, filePreviewURL } = useAppConfig(
  import.meta.env,
  import.meta.env.PROD,
);

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

function requiresBrowserAuthentication(url: URL) {
  return url.pathname.startsWith(
    '/admin-api/system/party-file/attachment/access',
  );
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
 * Build the local preview-service URL for an OA file.
 *
 * The preview service must fetch the file URL itself, so the backend file
 * endpoint is intentionally kept as the Base64-encoded `url` query parameter.
 * KKFileView 4.1.0 decodes this parameter before fetching it. Only HTTP(S)
 * sources can be delegated to KKFileView; browser-local sources and
 * permission-bound attachment endpoints must keep their original URL because
 * KKFileView cannot forward the browser session.
 */
export function getOaFilePreviewUrl(fileUrl: string) {
  const normalizedFileUrl = (fileUrl || '').trim();
  const previewEndpoint = filePreviewURL.trim();
  if (!normalizedFileUrl || !previewEndpoint) {
    return normalizedFileUrl;
  }
  try {
    const baseUrl =
      typeof window === 'undefined'
        ? 'http://localhost/'
        : window.location.origin;
    const sourceUrl = new URL(normalizedFileUrl, baseUrl);
    if (
      !['http:', 'https:'].includes(sourceUrl.protocol) ||
      requiresBrowserAuthentication(sourceUrl)
    ) {
      return normalizedFileUrl;
    }
    const previewUrl = new URL(previewEndpoint, baseUrl);
    const previewFetchUrl = resolvePreviewFetchUrl(sourceUrl, baseUrl);
    const bytes = new TextEncoder().encode(previewFetchUrl);
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

/**
 * A preview service in Docker cannot use the browser's localhost address.
 * This optional origin is only used in KKFileView's server-side fetch URL;
 * browser navigation and SSO redirects remain unchanged.
 */
function resolvePreviewFetchUrl(sourceUrl: URL, browserOrigin: string) {
  const fetchOrigin = filePreviewFetchOrigin.trim();
  if (!fetchOrigin || sourceUrl.origin !== browserOrigin) {
    return sourceUrl.toString();
  }
  try {
    const fetchBaseUrl = new URL(fetchOrigin);
    if (!['http:', 'https:'].includes(fetchBaseUrl.protocol)) {
      return sourceUrl.toString();
    }
    return new URL(
      `${sourceUrl.pathname}${sourceUrl.search}${sourceUrl.hash}`,
      fetchBaseUrl,
    ).toString();
  } catch {
    return sourceUrl.toString();
  }
}
