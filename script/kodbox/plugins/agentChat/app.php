<?php
class agentChatPlugin extends PluginBase{
    function __construct(){ parent::__construct(); }
    public function regist(){ $this->hookRegist(array('user.commonJs.insert' => 'agentChatPlugin.echoJs')); }
    public function echoJs(){ $this->echoFile('static/main.js'); }
    public function index(){
        if (!KodUser::isLogin()) { show_tips('用户未登录'); }
        $config = $this->getConfig(); $entryUrl = trim((string)_get($config, 'entryUrl', ''));
        if (!$entryUrl) { show_tips('插件入口地址未配置'); }
        $joiner = strpos($entryUrl, '?') === false ? '?' : '&'; $redirectUri = $entryUrl . $joiner . '_pluginRefresh=' . time();
        // 前端入口和 Java SSO 后端是两个不同服务，不能从 entryUrl 推导后端地址。
        // 旧版本配置没有 backendUrl 时，兼容本地 Java 默认端口 48080。
        $backendUrl = trim((string)_get($config, 'backendUrl', 'http://127.0.0.1:48080'));
        $parts = parse_url($backendUrl); $scheme = _get($parts, 'scheme', 'http'); $host = _get($parts, 'host', '');
        if (!$host) { show_tips('插件 SSO 后端地址配置无效'); } $port = isset($parts['port']) ? ':' . $parts['port'] : '';
        $token = Action('user.index')->accessToken();
        $url = $scheme . '://' . $host . $port . '/admin-api/system/auth/kod-sso/direct-login?kodAccessToken=' . rawurlencode($token) . '&redirectUri=' . rawurlencode($redirectUri);
        header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0'); header('Location: ' . $url); exit;
    }
}
