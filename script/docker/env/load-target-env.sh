#!/usr/bin/env bash

# Load one of the three deployment profiles into the current shell.
# Intended usage: source script/docker/env/load-target-env.sh 103

_target_env_loader_path="${BASH_SOURCE[0]}"
_target_env_loader_dir="$(cd "$(dirname "${_target_env_loader_path}")" && pwd)"
_target_env_loader_root="$(cd "${_target_env_loader_dir}/../../.." && pwd)"
_target_env_loader_executed=0
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  _target_env_loader_executed=1
fi

_target_env_loader_fail() {
  echo "[错误] $*" >&2
  if [[ "${_target_env_loader_executed}" -eq 1 ]]; then
    exit 1
  fi
  return 1
}

TARGET_ENV_NAME="${1:-${TARGET_ENV:-}}"
case "${TARGET_ENV_NAME}" in
  local|103|production) ;;
  *)
    _target_env_loader_fail "目标环境必须是 local、103 或 production。"
    return 1
    ;;
esac

TARGET_ENV_DIR="${_target_env_loader_dir}/targets"
TARGET_ENV_FILE="${TARGET_ENV_DIR}/${TARGET_ENV_NAME}.env"
TARGET_SECRETS_PATH="${TARGET_ENV_DIR}/${TARGET_ENV_NAME}.secrets.env"

if [[ ! -f "${TARGET_ENV_FILE}" ]]; then
  _target_env_loader_fail "目标环境文件不存在：${TARGET_ENV_FILE}"
  return 1
fi

# Prevent a previous profile's credentials from leaking into the next profile
# when multiple environments are loaded in one shell session.
unset MYSQL_ROOT_PASSWORD MASTER_DATASOURCE_PASSWORD SLAVE_DATASOURCE_PASSWORD
unset REDIS_PASSWORD REMOTE_PASSWORD

set -a
# shellcheck disable=SC1090
source "${TARGET_ENV_FILE}"
if [[ -f "${TARGET_SECRETS_PATH}" ]]; then
  # shellcheck disable=SC1090
  source "${TARGET_SECRETS_PATH}"
  TARGET_SECRETS_LOADED=true
else
  TARGET_SECRETS_LOADED=false
fi
set +a

# The profile name is authoritative even if an inherited shell had another value.
TARGET_ENV="${TARGET_ENV_NAME}"
TARGET_ENV_ROOT="${_target_env_loader_root}"
TARGET_ENV_FILE="${TARGET_ENV_FILE}"
TARGET_SECRETS_PATH="${TARGET_SECRETS_PATH}"
export TARGET_ENV TARGET_ENV_ROOT TARGET_ENV_FILE TARGET_SECRETS_PATH TARGET_SECRETS_LOADED

unset _target_env_loader_path _target_env_loader_dir _target_env_loader_root _target_env_loader_executed

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "已加载目标环境：${TARGET_ENV}"
  echo "配置文件：${TARGET_ENV_FILE}"
  if [[ "${TARGET_SECRETS_LOADED}" == true ]]; then
    echo "机密 overlay：${TARGET_SECRETS_PATH}"
  else
    echo "机密 overlay：未找到（仅加载非机密配置）"
  fi
fi
