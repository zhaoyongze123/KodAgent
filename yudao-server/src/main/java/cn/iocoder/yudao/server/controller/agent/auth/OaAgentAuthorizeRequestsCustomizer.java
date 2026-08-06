package cn.iocoder.yudao.server.controller.agent.auth;

import cn.iocoder.yudao.framework.security.config.AuthorizeRequestsCustomizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AuthorizeHttpRequestsConfigurer;
import org.springframework.stereotype.Component;

/**
 * 让 Agent 受控接口进入 OaAgentAuthInterceptor。
 *
 * <p>这些接口不使用 OA 的 OAuth2 登录态，而是使用 X-Agent-Key +
 * X-Agent-Identity 进行二次认证。这里只负责绕过 Spring Security 的
 * 全局 authenticated 规则，真正的身份、租户和工具权限校验仍由
 * OaAgentAuthInterceptor 执行。</p>
 */
@Component
public class OaAgentAuthorizeRequestsCustomizer extends AuthorizeRequestsCustomizer {

    @Override
    public void customize(AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry registry) {
        registry
                // Agent 业务工具、草稿、运行记录、事件和模型解析接口
                .requestMatchers("/agent/**").permitAll()
                // 模型设置接口位于 admin-api 下，但同样使用 Agent 身份票据
                .requestMatchers(
                        "/admin-api/agent/model-providers/**",
                        "/admin-api/agent/models/**",
                        "/admin-api/agent/model-bindings/**"
                ).permitAll();
    }
}
