package cn.iocoder.yudao.server.controller.agent.auth;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import javax.annotation.Resource;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import cn.iocoder.yudao.framework.security.core.service.SecurityFrameworkService;
import cn.iocoder.yudao.server.controller.agent.identity.OaAgentIdentityProperties;
import cn.iocoder.yudao.server.controller.agent.identity.OaAgentIdentityTicketService;
import cn.iocoder.yudao.server.controller.agent.AgentDocumentArtifactProperties;

/**
 * Business Agent facade 认证配置。
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
        OaAgentAuthProperties.class,
        OaAgentIdentityProperties.class,
        AgentDocumentArtifactProperties.class
})
public class OaAgentAuthConfiguration implements WebMvcConfigurer {

    @Resource
    private OaAgentAuthProperties properties;
    @Resource
    private cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService tenantFrameworkService;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private OaAgentIdentityProperties identityProperties;
    @Resource
    private OaAgentIdentityTicketService identityTicketService;
    @Resource
    private SecurityFrameworkService securityFrameworkService;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new OaAgentAuthInterceptor(properties, tenantFrameworkService, adminUserService,
                        identityProperties, identityTicketService, securityFrameworkService))
                .addPathPatterns(
                        "/agent/tools/**",
                        "/agent/drafts/**",
                        // 通用附件同样以 X-Agent-Key + 当前用户身份票据访问；不能
                        // 因为不属于某个业务领域就绕开租户、所有者和工具权限校验。
                        "/agent/artifacts/**",
                        "/agent/runs/**",
                        "/agent/threads/**",
                        "/agent/approvals/**",
                        "/agent/config/**",
                        "/agent/internal/models/**",
                        // Model settings are exposed under admin-api, but are
                        // authenticated by the same Agent identity ticket.
                        "/admin-api/agent/model-providers/**",
                        "/admin-api/agent/models/**",
                        "/admin-api/agent/model-bindings/**"
                );
    }
}
