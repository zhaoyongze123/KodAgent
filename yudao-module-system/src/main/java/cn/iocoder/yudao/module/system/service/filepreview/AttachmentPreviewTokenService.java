package cn.iocoder.yudao.module.system.service.filepreview;

import cn.hutool.core.util.StrUtil;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.annotation.PostConstruct;
import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.UUID;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.FILE_PREVIEW_TOKEN_INVALID;

/**
 * 为本地预览服务生成短时、不可伪造的 OA 文件源地址。
 */
@Component
public class AttachmentPreviewTokenService {

    private static final String TOKEN_VERSION = "v1";
    private static final String PREVIEW_CONTENT_PATH = "/admin-api/system/file-preview/content?token=";
    private static final String HMAC_ALGORITHM = "HmacSHA256";

    @Value("${OA_FILE_PREVIEW_TOKEN_SECRET:}")
    private String configuredSecret;

    @Value("${yudao.file-preview.token-expire-seconds:300}")
    private long expireSeconds = 300L;

    private byte[] secret;

    @PostConstruct
    public void initialize() {
        ensureInitialized();
    }

    public String createPreviewUrl(PreviewSource source, Long resourceId, Long fileId, Long userId) {
        return createPreviewUrl(source, resourceId, fileId, userId, null);
    }

    public String createPreviewUrl(PreviewSource source, Long resourceId, Long fileId, Long userId,
                                   String fileName) {
        if (source == null || resourceId == null || fileId == null || fileId <= 0) {
            throw invalidToken();
        }
        ensureInitialized();
        long expiresAt = currentEpochSeconds() + expireSeconds;
        String userIdValue = userId == null ? "" : String.valueOf(userId);
        String payload = TOKEN_VERSION + "|" + source.code + "|" + resourceId + "|" + fileId
                + "|" + userIdValue + "|" + expiresAt + "|" + UUID.randomUUID().toString().replace("-", "");
        String encodedPayload = encode(payload.getBytes(StandardCharsets.UTF_8));
        String previewUrl = PREVIEW_CONTENT_PATH + encodedPayload + "." + encode(sign(encodedPayload));
        if (StrUtil.isNotBlank(fileName)) {
            previewUrl += "&fullfilename=" + encodeFileName(fileName);
        }
        return previewUrl;
    }

    private String encodeFileName(String fileName) {
        try {
            return URLEncoder.encode(fileName, StandardCharsets.UTF_8.name());
        } catch (UnsupportedEncodingException e) {
            throw new IllegalStateException("无法编码文件名", e);
        }
    }

    public PreviewToken verify(String token) {
        ensureInitialized();
        try {
            String[] parts = StrUtil.trimToEmpty(token).split("\\.", -1);
            if (parts.length != 2) {
                throw invalidToken();
            }
            byte[] payloadBytes = decode(parts[0]);
            byte[] actualSignature = decode(parts[1]);
            byte[] expectedSignature = sign(parts[0]);
            if (!MessageDigest.isEqual(actualSignature, expectedSignature)) {
                throw invalidToken();
            }
            String[] fields = new String(payloadBytes, StandardCharsets.UTF_8).split("\\|", -1);
            if (fields.length != 7 || !TOKEN_VERSION.equals(fields[0])) {
                throw invalidToken();
            }
            PreviewSource source = PreviewSource.fromCode(fields[1]);
            Long resourceId = parsePositiveLong(fields[2]);
            Long fileId = parsePositiveLong(fields[3]);
            Long userId = StrUtil.isBlank(fields[4]) ? null : parsePositiveLong(fields[4]);
            long expiresAt = Long.parseLong(fields[5]);
            if (expiresAt <= currentEpochSeconds()) {
                throw invalidToken();
            }
            return new PreviewToken(source, resourceId, fileId, userId, expiresAt);
        } catch (IllegalArgumentException ex) {
            throw invalidToken();
        }
    }

    private Long parsePositiveLong(String value) {
        long parsed = Long.parseLong(value);
        if (parsed <= 0) {
            throw invalidToken();
        }
        return parsed;
    }

    private byte[] sign(String value) {
        try {
            javax.crypto.Mac mac = javax.crypto.Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new javax.crypto.spec.SecretKeySpec(secret, HMAC_ALGORITHM));
            return mac.doFinal(value.getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("无法初始化文件预览签名算法", e);
        }
    }

    private String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private byte[] decode(String value) {
        return Base64.getUrlDecoder().decode(value);
    }

    private long currentEpochSeconds() {
        return System.currentTimeMillis() / 1000L;
    }

    private synchronized void ensureInitialized() {
        if (secret != null) {
            return;
        }
        String secretValue = StrUtil.trim(configuredSecret);
        if (StrUtil.isBlank(secretValue)) {
            byte[] randomSecret = new byte[32];
            new SecureRandom().nextBytes(randomSecret);
            secretValue = encode(randomSecret);
        }
        secret = secretValue.getBytes(StandardCharsets.UTF_8);
        if (expireSeconds <= 0) {
            expireSeconds = 300L;
        }
    }

    private RuntimeException invalidToken() {
        return exception(FILE_PREVIEW_TOKEN_INVALID);
    }

    public enum PreviewSource {
        PARTY_FILE("party-file"),
        NOTICE("notice");

        private final String code;

        PreviewSource(String code) {
            this.code = code;
        }

        private static PreviewSource fromCode(String code) {
            for (PreviewSource source : values()) {
                if (source.code.equals(code)) {
                    return source;
                }
            }
            throw new IllegalArgumentException("unknown preview source");
        }
    }

    public static final class PreviewToken {
        private final PreviewSource source;
        private final Long resourceId;
        private final Long fileId;
        private final Long userId;
        private final long expiresAt;

        private PreviewToken(PreviewSource source, Long resourceId, Long fileId, Long userId, long expiresAt) {
            this.source = source;
            this.resourceId = resourceId;
            this.fileId = fileId;
            this.userId = userId;
            this.expiresAt = expiresAt;
        }

        public PreviewSource getSource() {
            return source;
        }

        public Long getResourceId() {
            return resourceId;
        }

        public Long getFileId() {
            return fileId;
        }

        public Long getUserId() {
            return userId;
        }

        public long getExpiresAt() {
            return expiresAt;
        }
    }
}
