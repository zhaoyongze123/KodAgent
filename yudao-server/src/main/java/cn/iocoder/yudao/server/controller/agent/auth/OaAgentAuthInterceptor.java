package cn.iocoder.yudao.server.controller.agent.auth;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.security.core.service.SecurityFrameworkService;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.service.TenantFrameworkService;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import cn.iocoder.yudao.server.controller.agent.identity.OaAgentIdentityProperties;
import cn.iocoder.yudao.server.controller.agent.identity.OaAgentIdentityTicketService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.util.StringUtils;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Dify facade 的稳定入口认证。
 */
@RequiredArgsConstructor
public class OaAgentAuthInterceptor implements HandlerInterceptor {

    private final OaAgentAuthProperties properties;
    private final TenantFrameworkService tenantFrameworkService;
    private final AdminUserService adminUserService;
    private final OaAgentIdentityProperties identityProperties;
    private final OaAgentIdentityTicketService identityTicketService;
    private final SecurityFrameworkService securityFrameworkService;

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (!Boolean.TRUE.equals(properties.getEnabled())) {
            return writeError(response, HttpStatus.SERVICE_UNAVAILABLE.value(), "Business Agent facade 认证未启用", "auth_disabled");
        }
        if (!StringUtils.hasText(properties.getApiKey())) {
            return writeError(response, HttpStatus.SERVICE_UNAVAILABLE.value(), "未配置 Business Agent API Key", "api_key_not_configured");
        }
        String actualKey = request.getHeader(properties.getHeaderName());
        if (!sameKey(properties.getApiKey(), actualKey)) {
            return writeError(response, HttpStatus.UNAUTHORIZED.value(), "Business Agent API Key 无效", "api_key_invalid");
        }

        try {
            LoginUser loginUser = resolveLoginUser(request);
            TenantContextHolder.setTenantId(loginUser.getTenantId());
            TenantContextHolder.setIgnore(false);
            tenantFrameworkService.validTenant(loginUser.getTenantId());
            SecurityFrameworkUtils.setLoginUser(loginUser, request);
            validateToolPermission(request);
            return true;
        } catch (AgentAuthorizationException ex) {
            return writeError(response, HttpStatus.FORBIDDEN.value(), ex.getMessage(), ex.reason);
        } catch (RuntimeException ex) {
            return writeError(response, HttpStatus.UNAUTHORIZED.value(), ex.getMessage() == null
                    ? "Business Agent 服务账号认证失败" : ex.getMessage(), classifyReason(ex));
        }
    }

    private void validateToolPermission(HttpServletRequest request) {
        String requested = request.getHeader("X-Agent-Permission");
        if (!StringUtils.hasText(requested)) {
            throw new IllegalArgumentException("缺少 X-Agent-Permission 工具权限");
        }
        // Agent 契约使用稳定的领域权限名，Java 负责映射到 OA 的真实权限。
        if ("agent:progress".equals(requested) || "agent:audit".equals(requested)
                || "agent:conversation".equals(requested) || "agent:contract".equals(requested)) {
            return;
        }
        Map<String, String[]> mapping = new LinkedHashMap<>();
        mapping.put("meeting:read", new String[]{"system:meeting-room:query", "system:meeting-booking:query"});
        mapping.put("meeting:booking:create", new String[]{"system:meeting-booking:update"});
        // Agent approvals are tenant/owner scoped records shared by BPM,
        // meeting and personal-schedule drafts. The common card endpoint
        // therefore accepts a permission from any of those domains; it does
        // not grant visibility beyond the record's existing owner check.
        mapping.put("approval:read", new String[]{"bpm:task:query", "bpm:process-instance:query", "system:meeting-booking:query",
                "system:meeting-booking:update", "system:personal-schedule:query", "system:personal-schedule:write"});
        mapping.put("approval:write", new String[]{"bpm:task:update", "bpm:oa-leave:create",
                "bpm:process-instance:cancel", "system:meeting-booking:update",
                "system:personal-schedule:write"});
        mapping.put("schedule:read", new String[]{"system:personal-schedule:query"});
        mapping.put("schedule:write", new String[]{"system:personal-schedule:write"});
        mapping.put("party-file:read", new String[]{"system:party-file:query"});
        mapping.put("party-file:create", new String[]{"system:party-file:create"});
        mapping.put("party-file:update", new String[]{"system:party-file:update"});
        mapping.put("party-file:delete", new String[]{"system:party-file:delete"});
        mapping.put("party-file:attachment:write", new String[]{"system:party-file:update"});
        mapping.put("model:read", new String[]{"system:agent-model:query"});
        mapping.put("model:manage", new String[]{"system:agent-model:manage"});
        // 运行台展示跨用户的全院聚合与追踪，不能复用所有人均可写事件的 agent:audit。
        mapping.put("agent:analytics:read", new String[]{"system:agent-model:manage"});
        String[] permissions = mapping.get(requested);
        if (permissions == null || !securityFrameworkService.hasAnyPermissions(permissions)) {
            throw new AgentAuthorizationException("当前用户没有调用该 Agent 工具的权限");
        }
    }

    private LoginUser resolveLoginUser(HttpServletRequest request) {
        String identityTicket = request.getHeader(identityProperties.getHeaderName());
        if (!StringUtils.hasText(identityTicket)) {
            throw new IllegalArgumentException("缺少 X-Agent-Identity 用户身份票据");
        }
        OaAgentIdentityTicketService.IdentityPayload payload = identityTicketService.verify(identityTicket);
        TenantContextHolder.setTenantId(payload.getTenantId());
        TenantContextHolder.setIgnore(false);
        return buildLoginUser(payload.getUserId(), payload.getTenantId());
    }

    private LoginUser buildLoginUser(Long userId, Long tenantId) {
        adminUserService.validateUserList(java.util.Collections.singletonList(userId));
        AdminUserDO user = adminUserService.getUser(userId);
        if (user == null || !tenantId.equals(user.getTenantId())) {
            throw new IllegalArgumentException("Business Agent 用户不存在或不属于当前租户");
        }
        HashMap<String, String> info = new HashMap<>();
        info.put(LoginUser.INFO_KEY_NICKNAME, user.getNickname());
        if (user.getDeptId() != null) {
            info.put(LoginUser.INFO_KEY_DEPT_ID, String.valueOf(user.getDeptId()));
        }
        return new LoginUser().setId(userId)
                .setUserType(UserTypeEnum.ADMIN.getValue())
                .setTenantId(tenantId)
                .setInfo(info);
    }

    private boolean writeError(HttpServletResponse response, int status, String message, String reason) {
        response.setStatus(status);
        response.setHeader("X-Agent-Auth-Failure", reason);
        CommonResult<Map<String, String>> result = CommonResult.error(status, message);
        result.setData(java.util.Collections.singletonMap("authFailureReason", reason));
        ServletUtils.writeJSON(response, result);
        return false;
    }

    private String classifyReason(RuntimeException ex) {
        String message = ex.getMessage() == null ? "" : ex.getMessage();
        if (message.contains("身份票据") || message.contains("用户身份")) return "identity_ticket_invalid";
        if (message.contains("租户") || message.contains("用户不存在")) return "identity_scope_invalid";
        if (message.contains("权限")) return "permission_header_invalid";
        return "authentication_failed";
    }

    private boolean sameKey(String expected, String actual) {
        if (actual == null) {
            return false;
        }
        return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), actual.getBytes(StandardCharsets.UTF_8));
    }

    private static final class AgentAuthorizationException extends RuntimeException {
        private final String reason;

        private AgentAuthorizationException(String message) {
            this(message, "permission_denied");
        }

        private AgentAuthorizationException(String message, String reason) {
            super(message);
            this.reason = reason;
        }
    }
}
