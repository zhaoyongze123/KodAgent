package cn.iocoder.yudao.server.controller.agent.auth;

import cn.iocoder.yudao.framework.common.biz.system.oauth2.OAuth2TokenCommonApi;
import cn.iocoder.yudao.framework.common.biz.system.oauth2.dto.OAuth2AccessTokenCheckRespDTO;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.AuthLoginReqVO;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.AuthLoginRespVO;
import cn.iocoder.yudao.module.system.service.auth.AdminAuthService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;

/**
 * 管理 facade 服务账号的登录、刷新和 token 校验。
 *
 * token 只保存在当前服务实例内，不会返回给 Dify，也不会写入日志。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OaAgentAuthTokenManager {

    private final AdminAuthService adminAuthService;
    private final OAuth2TokenCommonApi oauth2TokenApi;
    private final OaAgentAuthProperties properties;

    private AuthLoginRespVO token;

    public synchronized LoginUser getLoginUser() {
        validateConfiguration();

        OAuth2AccessTokenCheckRespDTO accessToken = checkCurrentToken();
        if (accessToken == null) {
            accessToken = refreshOrLogin();
        }
        if (accessToken == null) {
            throw new IllegalStateException("Business Agent 服务账号认证失败");
        }
        return new LoginUser()
                .setId(accessToken.getUserId())
                .setUserType(accessToken.getUserType())
                .setInfo(accessToken.getUserInfo())
                .setTenantId(accessToken.getTenantId())
                .setScopes(accessToken.getScopes())
                .setExpiresTime(accessToken.getExpiresTime());
    }

    private OAuth2AccessTokenCheckRespDTO checkCurrentToken() {
        if (token == null || token.getAccessToken() == null) {
            return null;
        }
        if (token.getExpiresTime() != null
                && !token.getExpiresTime().isAfter(LocalDateTime.now().plusSeconds(properties.getRefreshAheadSeconds()))) {
            return null;
        }
        try {
            return oauth2TokenApi.checkAccessToken(token.getAccessToken());
        } catch (RuntimeException ex) {
            log.debug("Business Agent access token 校验失败，将尝试刷新或重新登录", ex);
            return null;
        }
    }

    private OAuth2AccessTokenCheckRespDTO refreshOrLogin() {
        if (token != null && token.getRefreshToken() != null) {
            try {
                token = adminAuthService.refreshToken(token.getRefreshToken());
                OAuth2AccessTokenCheckRespDTO refreshed = checkCurrentToken();
                if (refreshed != null) {
                    return refreshed;
                }
            } catch (RuntimeException ex) {
                log.info("Business Agent refresh token 失败，将重新登录服务账号");
            }
        }

        AuthLoginReqVO request = new AuthLoginReqVO();
        request.setUsername(properties.getUsername());
        request.setPassword(properties.getPassword());
        token = adminAuthService.login(request);
        return checkCurrentToken();
    }

    private void validateConfiguration() {
        if (properties.getUsername() == null || properties.getUsername().trim().isEmpty()
                || properties.getPassword() == null || properties.getPassword().trim().isEmpty()) {
            throw new IllegalStateException("未配置 Business Agent 服务账号，请设置 OA_AGENT_USERNAME 和 OA_AGENT_PASSWORD");
        }
    }
}
