const ADMIN_ROLE_CODES = new Set(['super_admin', 'dept_admin']);
const REMOVED_HOME_PATHS = new Set(['/analytics', '/workspace', '/dashboard']);
const OA_LITE_HOME_PATH = '/oa-lite';
const ADMIN_DEFAULT_HOME_PATH = '/bpm/manager/model';

export function isAdminUser(roles: string[] = []) {
  return roles.some((role) => ADMIN_ROLE_CODES.has(role));
}

export function resolveAdminHomePath(homePath?: string) {
  if (!homePath || REMOVED_HOME_PATHS.has(homePath)) {
    return ADMIN_DEFAULT_HOME_PATH;
  }
  return homePath;
}

export function resolveUserHomePath(
  homePath?: string,
  roles: string[] = [],
) {
  if (!isAdminUser(roles)) {
    return OA_LITE_HOME_PATH;
  }
  return resolveAdminHomePath(homePath);
}

export { ADMIN_DEFAULT_HOME_PATH, OA_LITE_HOME_PATH };
