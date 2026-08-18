package cn.iocoder.yudao.server.controller.agent.identity;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.UUID;

/**
 * 签发和校验短期 Agent 身份票据。
 */
@Service
@RequiredArgsConstructor
public class OaAgentIdentityTicketService {

    private static final String HMAC_ALGORITHM = "HmacSHA256";
    private static final long CLOCK_SKEW_SECONDS = 30L;

    private final OaAgentIdentityProperties properties;

    public String issue(Long userId, Long tenantId) {
        if (userId == null || tenantId == null) {
            throw new IllegalArgumentException("当前登录用户缺少用户或租户信息");
        }
        long issuedAt = Instant.now().getEpochSecond();
        IdentityPayload payload = new IdentityPayload(userId, tenantId, issuedAt,
                issuedAt + properties.getTtlSeconds(), UUID.randomUUID().toString());
        String encodedPayload = encode(JsonUtils.toJsonByte(payload));
        return encodedPayload + "." + encode(sign(encodedPayload));
    }

    public IdentityPayload verify(String ticket) {
        requireSecret();
        if (!StringUtils.hasText(ticket)) {
            throw new IllegalArgumentException("缺少 Agent 用户身份票据");
        }
        String[] parts = ticket.split("\\.", -1);
        if (parts.length != 2 || !StringUtils.hasText(parts[0]) || !StringUtils.hasText(parts[1])) {
            throw new IllegalArgumentException("Agent 用户身份票据格式无效");
        }
        byte[] actualSignature;
        try {
            actualSignature = Base64.getUrlDecoder().decode(parts[1]);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Agent 用户身份票据签名无效");
        }
        if (!MessageDigest.isEqual(sign(parts[0]), actualSignature)) {
            throw new IllegalArgumentException("Agent 用户身份票据签名无效");
        }
        IdentityPayload payload;
        try {
            payload = JsonUtils.parseObject(Base64.getUrlDecoder().decode(parts[0]), IdentityPayload.class);
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("Agent 用户身份票据内容无效");
        }
        validatePayload(payload);
        return payload;
    }

    private void validatePayload(IdentityPayload payload) {
        if (payload == null || payload.getUserId() == null || payload.getTenantId() == null
                || payload.getIssuedAt() == null || payload.getExpiresAt() == null
                || !StringUtils.hasText(payload.getNonce())) {
            throw new IllegalArgumentException("Agent 用户身份票据字段不完整");
        }
        long now = Instant.now().getEpochSecond();
        if (payload.getIssuedAt() > now + CLOCK_SKEW_SECONDS) {
            throw new IllegalArgumentException("Agent 用户身份票据签发时间无效");
        }
        if (payload.getExpiresAt() <= now) {
            throw new IllegalArgumentException("Agent 用户身份票据已过期");
        }
        if (payload.getExpiresAt() <= payload.getIssuedAt()
                || payload.getExpiresAt() - payload.getIssuedAt() > properties.getTtlSeconds()) {
            throw new IllegalArgumentException("Agent 用户身份票据有效期无效");
        }
    }

    private byte[] sign(String payload) {
        requireSecret();
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(properties.getSecret().getBytes(StandardCharsets.UTF_8), HMAC_ALGORITHM));
            return mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
        } catch (Exception ex) {
            throw new IllegalStateException("Agent 用户身份票据签名失败", ex);
        }
    }

    private void requireSecret() {
        if (!StringUtils.hasText(properties.getSecret()) || properties.getSecret().length() < 32) {
            throw new IllegalStateException("OA_AGENT_IDENTITY_SECRET 未配置或长度不足 32 位");
        }
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class IdentityPayload {
        private Long userId;
        private Long tenantId;
        private Long issuedAt;
        private Long expiresAt;
        private String nonce;
    }
}
