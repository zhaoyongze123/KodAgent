package cn.iocoder.yudao.server.controller.agent.identity;

import cn.iocoder.yudao.server.controller.agent.auth.OaAgentAuthProperties;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.security.PermitAll;
import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - Agent 身份")
@RestController
@RequestMapping("/admin-api/agent/identity")
public class OaAgentIdentityController {

    @Resource
    private OaAgentIdentityTicketService ticketService;
    @Resource
    private OaAgentIdentityProperties properties;
    @Resource
    private OaAgentAuthProperties authProperties;

    @PostMapping("/ticket")
    @Operation(summary = "为当前 OA 登录用户签发短期 Agent 身份票据")
    public CommonResult<Map<String, Object>> issueTicket() {
        LoginUser loginUser = SecurityFrameworkUtils.getLoginUser();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ticket", ticketService.issue(loginUser.getId(), loginUser.getTenantId()));
        result.put("expiresIn", properties.getTtlSeconds());
        return success(result);
    }

    @GetMapping("/session")
    @PermitAll
    @Operation(summary = "校验 Agent 身份会话")
    public CommonResult<Map<String, Object>> validateSession(
            @RequestHeader(value = "X-Agent-Key", required = false) String agentKey,
            @RequestHeader(value = "X-Agent-Identity", required = false) String identityTicket) {
        if (!sameKey(authProperties.getApiKey(), agentKey)) {
            return CommonResult.error(401, "Agent API Key 无效");
        }
        OaAgentIdentityTicketService.IdentityPayload payload;
        try {
            payload = ticketService.verify(identityTicket);
        } catch (IllegalArgumentException ex) {
            // 过期、格式错误或签名错误都是当前登录会话失效，不能返回 500。
            // Next.js 据此清理 Cookie 并重新发起 SSO，避免页面永久停在登录中。
            return CommonResult.error(401, "Agent 用户身份票据已失效");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("authenticated", true);
        result.put("userId", payload.getUserId());
        result.put("tenantId", payload.getTenantId());
        result.put("expiresAt", payload.getExpiresAt());
        return success(result);
    }

    @PostMapping("/renew")
    @PermitAll
    @Operation(summary = "续期 Agent 身份会话")
    public CommonResult<Map<String, Object>> renew(
            @RequestHeader(value = "X-Agent-Key", required = false) String agentKey,
            @RequestHeader(value = "X-Agent-Identity", required = false) String identityTicket) {
        if (!sameKey(authProperties.getApiKey(), agentKey)) {
            return CommonResult.error(401, "Agent API Key 无效");
        }
        OaAgentIdentityTicketService.IdentityPayload payload;
        try {
            payload = ticketService.verify(identityTicket);
        } catch (IllegalArgumentException ex) {
            return CommonResult.error(401, "Agent 用户身份票据已失效");
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ticket", ticketService.issue(payload.getUserId(), payload.getTenantId()));
        result.put("expiresIn", properties.getTtlSeconds());
        result.put("expiresAt", System.currentTimeMillis() / 1000L + properties.getTtlSeconds());
        return success(result);
    }

    private boolean sameKey(String expected, String actual) {
        if (!StringUtils.hasText(expected) || !StringUtils.hasText(actual)) {
            return false;
        }
        return MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                actual.getBytes(StandardCharsets.UTF_8));
    }
}
