package cn.iocoder.yudao.module.system.service.auth;

import cn.iocoder.yudao.module.system.controller.admin.auth.vo.AuthLoginRespVO;

import javax.servlet.http.HttpServletRequest;

public interface KodSsoService {

    String buildAuthorizeRedirectUrl(HttpServletRequest request, String redirectUri);

    AuthLoginRespVO loginByKodToken(String kodAccessToken);

    String buildClientRedirectUrl(String kodAccessToken, String redirectUri);

    AuthLoginRespVO exchangeCode(String code);

    /**
     * 获取当前本地用户最近一次可道云单点登录时保存的用户令牌。
     */
    String getCurrentUserKodAccessToken(Long userId);

    /**
     * 获取可道云地址，供需要按当前用户权限访问可道云的业务使用。
     */
    String getKodBaseUrl();

}
