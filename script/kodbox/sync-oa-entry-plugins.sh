#!/usr/bin/env bash
set -euo pipefail

PLUGIN_BASE_DIR="${PLUGIN_BASE_DIR:-/root/deployments/kodbox/data/plugins}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

write_app() {
  local plugin_dir="$1"
  local class_name="$2"
  local target_file="${PLUGIN_BASE_DIR}/${plugin_dir}/app.php"

  python3 - "$class_name" "$target_file" <<'PY'
from pathlib import Path
import sys

class_name = sys.argv[1]
target_file = Path(sys.argv[2])
target_file.parent.mkdir(parents=True, exist_ok=True)

template = """<?php
class __CLASS_NAME__ extends PluginBase{
    function __construct(){
        parent::__construct();
    }
    public function regist(){
        $this->hookRegist(array(
            'user.commonJs.insert' => '__CLASS_NAME__.echoJs'
        ));
    }
    public function echoJs(){
        $this->echoFile('static/main.js');
    }
    public function index(){
        if (!KodUser::isLogin()) {
            show_tips('用户未登录');
        }
        $config = $this->getConfig();
        $entryUrl = trim((string)_get($config, 'entryUrl', ''));
        if (!$entryUrl) {
            show_tips('插件入口地址未配置');
        }

        $entryParts = parse_url($entryUrl);
        $scheme = _get($entryParts, 'scheme', 'https');
        $host = _get($entryParts, 'host', '');
        if (!$host) {
            show_tips('插件入口地址配置无效');
        }
        $port = isset($entryParts['port']) ? ':' . $entryParts['port'] : '';
        $tenantId = trim((string)_get($config, 'tenantId', '1'));
        if (!ctype_digit($tenantId) || (int)$tenantId <= 0) {
            show_tips('OA 租户编号配置无效');
        }
        $hashPos = strpos($entryUrl, '#');
        if ($hashPos === false) {
            $targetRoute = _get($entryParts, 'path', '/') . (
                isset($entryParts['query']) ? '?' . $entryParts['query'] : ''
            );
            $clientBaseUrl = $scheme . '://' . $host . $port;
        } else {
            $targetRoute = substr($entryUrl, $hashPos + 1);
            $clientBaseUrl = substr($entryUrl, 0, $hashPos);
        }
        $targetRoute = '/' . ltrim($targetRoute, '/');
        // 先进入 OA 白名单 SSO 路由，换票后再由 OA 前端跳到实际业务页面。
        $redirectUri = rtrim($clientBaseUrl, '/') . '/#/auth/kod-sso-login?tenantId='
            . rawurlencode($tenantId)
            . '&redirect=' . rawurlencode($targetRoute);
        $kodAccessToken = Action('user.index')->accessToken();
        $directLoginUrl = $scheme . '://' . $host . $port
            . '/admin-api/system/auth/kod-sso/direct-login?kodAccessToken='
            . rawurlencode($kodAccessToken)
            . '&redirectUri=' . rawurlencode($redirectUri);
        header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
        header('Pragma: no-cache');
        header('Location: ' . $directLoginUrl);
        exit;
    }
}
"""

target_file.write_text(template.replace('__CLASS_NAME__', class_name))
PY

  echo "[完成] 已写入 ${target_file}"
}

write_main() {
  local plugin_dir="$1"
  local page_id="$2"
  local icon="$3"
  local target_file="${PLUGIN_BASE_DIR}/${plugin_dir}/static/main.js"

  python3 - "$plugin_dir" "$page_id" "$icon" "$target_file" <<'PY'
from pathlib import Path
import sys

plugin_dir = sys.argv[1]
page_id = sys.argv[2]
icon = sys.argv[3]
target_file = Path(sys.argv[4])
target_file.parent.mkdir(parents=True, exist_ok=True)

template = """kodReady.push(function(){
    var pageId = '__PAGE_ID__';
    var pageTitle = '{{package.name}}';
    var pluginUrl = '/index.php?plugin/__PLUGIN_DIR__/index';

    function buildFreshUrl() {
        return pluginUrl + '&_pluginRefresh=' + Date.now();
    }

    Events.bind('main.menu.loadBefore', function(listData){
        listData[pageId] = {
            name: pageTitle,
            url: pluginUrl,
            target: '{{config.openWith}}',
            subMenu: '{{config.menuSubMenu}}',
            menuAdd: '{{config.menuAdd}}',
            icon: '__ICON__'
        };
    });

    Router.mapIframe({
        page: pageId,
        title: pageTitle,
        url: buildFreshUrl(),
        ignoreLogin: false
    });
});
"""

content = template.replace('__PLUGIN_DIR__', plugin_dir).replace('__PAGE_ID__', page_id).replace('__ICON__', icon)
target_file.write_text(content)
PY

  echo "[完成] 已写入 ${target_file}"
}

write_package() {
  local plugin_dir="$1"
  local plugin_name="$2"
  local target_file="${PLUGIN_BASE_DIR}/${plugin_dir}/package.json"

  python3 - "$plugin_dir" "$plugin_name" "$target_file" <<'PY'
from pathlib import Path
import json
import sys

plugin_id, plugin_name, target = sys.argv[1:]
target_file = Path(target)
target_file.parent.mkdir(parents=True, exist_ok=True)
package = {
    "id": plugin_id,
    "name": plugin_name,
    "title": plugin_name,
    "version": "1.0.0",
    "category": "tools",
    "source": {"className": "font-icon ri-links-line"},
    "description": "OA intranet entry with KodBox SSO.",
    "auther": {"copyright": "OA", "homePage": ""},
    "configItem": {
        "entryUrl": {
            "type": "input",
            "value": "",
            "display": "入口地址",
            "desc": "OA 页面在 KodBox 内嵌打开的地址。",
            "require": 1
        },
        "tenantId": {
            "type": "input",
            "value": "1",
            "display": "OA 租户编号",
            "desc": "回跳 OA 时写入前端路由的租户编号。",
            "require": 1
        },
        "openWith": {
            "type": "segment",
            "value": "inline",
            "display": "{{LNG['admin.plugin.openWith']}}",
            "info": {
                "inline": "<i class='font-icon ri-layout-left-line-2'></i>{{LNG['explorer.app.openInline']}}",
                "dialog": "<i class='font-icon ri-picture-in-picture-fill'></i>{{LNG['explorer.app.openDialog']}}",
                "_blank": "<i class='font-icon ri-external-link-fill'></i>{{LNG['explorer.app.openWindow']}}"
            }
        },
        "sep1001": "<hr/>",
        "menuAdd": {
            "type": "switch",
            "value": 1,
            "display": "{{LNG['admin.plugin.menuAdd']}}",
            "desc": "{{LNG['admin.plugin.menuAddDesc']}}",
            "switchItem": {"0": "", "1": "menuSubMenu"}
        },
        "menuSubMenu": {
            "type": "switch",
            "value": 0,
            "display": "{{LNG['admin.setting.subMenu']}}",
            "desc": "{{LNG['admin.plugin.menuSubMenuDesc']}}"
        },
        "pluginAuth": {
            "type": "userSelect",
            "value": {"all": 1},
            "display": "{{LNG['admin.plugin.auth']}}",
            "desc": "{{LNG['admin.plugin.authDesc']}}",
            "require": 1
        }
    }
}
target_file.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
PY

  echo "[完成] 已写入 ${target_file}"
}

write_app "approvalCreateCenter" "approvalCreateCenterPlugin"
write_main "approvalCreateCenter" "{{package.id}}" "ri-draft-fill"
write_package "approvalCreateCenter" "审批中心"

write_app "meetingRoom" "meetingRoomPlugin"
write_main "meetingRoom" "{{package.id}}" "ri-team-fill"
write_package "meetingRoom" "会议室"

write_app "scheduleCenter" "scheduleCenterPlugin"
write_main "scheduleCenter" "{{package.id}}" "ri-calendar-check-fill"
write_package "scheduleCenter" "日程"

write_app "partyFile" "partyFilePlugin"
write_main "partyFile" "partyFileStandaloneV2" "ri-government-fill"
write_package "partyFile" "党务文件"

mkdir -p "${PLUGIN_BASE_DIR}/oaDeptSync"
cp "${SCRIPT_DIR}/oaDeptSync/app.php" "${PLUGIN_BASE_DIR}/oaDeptSync/app.php"
cp "${SCRIPT_DIR}/oaDeptSync/package.json" "${PLUGIN_BASE_DIR}/oaDeptSync/package.json"
echo "[完成] 已写入 ${PLUGIN_BASE_DIR}/oaDeptSync/app.php"
