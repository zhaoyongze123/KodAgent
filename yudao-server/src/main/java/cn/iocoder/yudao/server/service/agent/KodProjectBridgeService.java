package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.server.controller.agent.project.KodProjectProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * Java 到 KodCloud project 插件的只读事实适配器。
 *
 * <p>本类负责身份绑定、短期 HMAC 票据和响应解包。业务权限仍在 KodCloud
 * 项目插件内复核，Java 不直接连接 KodCloud 数据库。</p>
 */
@Service
public class KodProjectBridgeService {

    private static final String HMAC = "HmacSHA256";

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Resource
    private RestTemplate restTemplate;
    @Resource
    private KodProjectProperties properties;

    /** 查询当前 OA 用户绑定的 KodCloud 用户编号；没有绑定时明确失败。 */
    public long kodUserId(Long tenantId, Long oaUserId) {
        if (tenantId == null || oaUserId == null) {
            throw new IllegalStateException("KOD_USER_BINDING_REQUIRED");
        }
        try {
            Long result = jdbcTemplate.queryForObject(
                    "SELECT kod_user_id FROM agent_kod_user_binding "
                            + "WHERE tenant_id = ? AND oa_user_id = ? AND status = 'ACTIVE'",
                    Long.class, tenantId, oaUserId);
            if (result == null || result <= 0) throw bindingRequired();
            return result;
        } catch (RuntimeException ex) {
            if (ex.getMessage() != null && ex.getMessage().contains("KOD_USER_BINDING_REQUIRED")) throw ex;
            throw bindingRequired();
        }
    }

    /** 绑定 OA 用户与 KodCloud 用户；只允许管理员通过显式接口调用。 */
    public void bindUser(Long tenantId, Long oaUserId, Long kodUserId, Long operatorUserId) {
        if (tenantId == null || oaUserId == null || kodUserId == null || kodUserId <= 0) {
            throw new IllegalArgumentException("OA 用户和 KodCloud 用户编号不能为空");
        }
        jdbcTemplate.update("INSERT INTO agent_kod_user_binding "
                        + "(tenant_id, oa_user_id, kod_user_id, status, created_by, updated_at) "
                        + "VALUES (?, ?, ?, 'ACTIVE', ?, CURRENT_TIMESTAMP) "
                        + "ON CONFLICT (tenant_id, oa_user_id) DO UPDATE SET kod_user_id = EXCLUDED.kod_user_id, "
                        + "status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP, created_by = EXCLUDED.created_by",
                tenantId, oaUserId, kodUserId, operatorUserId);
    }

    /** 调用项目列表接口。 */
    public Map<String, Object> listProjects(Long tenantId, Long userId) {
        return call("projects", tenantId, userId, null, null);
    }

    /** 调用项目快照接口。 */
    public Map<String, Object> snapshot(Long tenantId, Long userId, long projectId) {
        return call("snapshot", tenantId, userId, projectId, null);
    }

    /** 调用项目任务接口。 */
    public Map<String, Object> tasks(Long tenantId, Long userId, long projectId) {
        return call("tasks", tenantId, userId, projectId, null);
    }

    /** 调用项目日志接口。 */
    public Map<String, Object> activity(Long tenantId, Long userId, long projectId) {
        return call("activity", tenantId, userId, projectId, null);
    }

    /** 调用项目文件元数据接口。 */
    public Map<String, Object> documents(Long tenantId, Long userId, long projectId) {
        return call("documents", tenantId, userId, projectId, null);
    }

    /** 调用项目文件正文接口；只供 Java 索引任务使用。 */
    public Map<String, Object> document(Long tenantId, Long userId, long projectId, long fileId) {
        return call("document", tenantId, userId, projectId, fileId);
    }

    /**
     * 浏览当前 KodCloud 用户可读的目录。folderId 为空时由插件返回用户根目录；
     * Java 只获得目录编号和展示名，不接触 KodCloud 路径或浏览器会话。
     */
    public Map<String, Object> knowledgeFolder(Long tenantId, Long userId, Long folderId) {
        return callFolder("knowledge_folder", tenantId, userId, folderId);
    }

    /** 当前用户在指定目录中实时可见的文件元数据，用于检索前版本和权限复核。 */
    public Map<String, Object> knowledgeDocuments(Long tenantId, Long userId, long folderId) {
        if (folderId <= 0) throw new IllegalArgumentException("知识目录编号必须为正整数");
        return callFolder("knowledge_documents", tenantId, userId, folderId);
    }

    /** 读取当前用户可见目录中的已枚举文件正文，仅供 Java 索引任务使用。 */
    public Map<String, Object> knowledgeDocument(Long tenantId, Long userId, long folderId, long fileId) {
        if (folderId <= 0 || fileId <= 0) throw new IllegalArgumentException("知识目录或文件编号必须为正整数");
        if (!StringUtils.hasText(properties.getBridgeSecret()) || properties.getBridgeSecret().length() < 32) {
            throw new IllegalStateException("项目桥接密钥未配置");
        }
        long kodUserId = kodUserId(tenantId, userId);
        return callAsKodUser("knowledge_document", tenantId, userId, kodUserId, null, fileId, folderId);
    }

    /**
     * 读取管理员配置的共享制度目录。目录访问固定使用单独的 KodCloud 只读服务账号，
     * 不会借用当前聊天用户的会话或令牌。
     */
    public Map<String, Object> policyDocuments(Long tenantId) {
        PolicyLibraryBinding binding = policyLibraryBinding(tenantId);
        return callAsKodUser("policy_documents", tenantId, 0L, binding.kodServiceUserId,
                null, null, binding.kodFolderId);
    }

    /** 读取共享制度目录内一个已枚举文件的正文，仅供 Java 索引任务使用。 */
    public Map<String, Object> policyDocument(Long tenantId, long fileId) {
        PolicyLibraryBinding binding = policyLibraryBinding(tenantId);
        return callAsKodUser("policy_document", tenantId, 0L, binding.kodServiceUserId,
                null, fileId, binding.kodFolderId);
    }

    /** 管理员配置共享制度目录及其独立的只读 KodCloud 服务账号。 */
    public void bindPolicyLibrary(Long tenantId, long folderId, long serviceKodUserId, Long operatorUserId) {
        if (tenantId == null || folderId <= 0 || serviceKodUserId <= 0) {
            throw new IllegalArgumentException("制度目录和 KodCloud 服务账号编号必须为正整数");
        }
        jdbcTemplate.update("INSERT INTO agent_policy_library_binding "
                        + "(tenant_id, kod_folder_id, kod_service_user_id, status, created_by, updated_at) "
                        + "VALUES (?, ?, ?, 'ACTIVE', ?, CURRENT_TIMESTAMP) "
                        + "ON CONFLICT (tenant_id) DO UPDATE SET kod_folder_id = EXCLUDED.kod_folder_id, "
                        + "kod_service_user_id = EXCLUDED.kod_service_user_id, status = 'ACTIVE', "
                        + "created_by = EXCLUDED.created_by, updated_at = EXCLUDED.updated_at",
                tenantId, folderId, serviceKodUserId, operatorUserId);
        // 目录或服务账号更换后，旧目录的索引不能继续作为制度依据；绑定接口会
        // 随后触发首次同步，当前目录中的文件再被逐个恢复为 READY。
        jdbcTemplate.update("UPDATE agent_knowledge_source SET extraction_status='INVALIDATED', "
                        + "invalidated_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                        + "WHERE tenant_id=? AND source_type='POLICY_LIBRARY' AND invalidated_at IS NULL",
                tenantId);
    }

    /** 当前租户是否已配置有效的共享制度库。 */
    public boolean hasPolicyLibrary(Long tenantId) {
        if (tenantId == null) return false;
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(1) FROM agent_policy_library_binding WHERE tenant_id=? AND status='ACTIVE'",
                Integer.class, tenantId);
        return count != null && count > 0;
    }

    /** 管理员停用制度库时同时使旧索引失效，避免停用后仍能检索历史制度内容。 */
    public void unbindPolicyLibrary(Long tenantId) {
        if (tenantId == null) return;
        jdbcTemplate.update("UPDATE agent_policy_library_binding SET status='DISABLED', "
                        + "updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?", tenantId);
        jdbcTemplate.update("UPDATE agent_knowledge_source SET extraction_status='INVALIDATED', "
                        + "invalidated_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                        + "WHERE tenant_id=? AND source_type='POLICY_LIBRARY' AND invalidated_at IS NULL",
                tenantId);
    }

    private Map<String, Object> call(String action, Long tenantId, Long userId, Long projectId, Long fileId) {
        if (!StringUtils.hasText(properties.getBridgeSecret()) || properties.getBridgeSecret().length() < 32) {
            throw new IllegalStateException("项目桥接密钥未配置");
        }
        long kodUserId = kodUserId(tenantId, userId);
        return callAsKodUser(action, tenantId, userId, kodUserId, projectId, fileId, null);
    }

    private Map<String, Object> callFolder(String action, Long tenantId, Long userId, Long folderId) {
        if (!StringUtils.hasText(properties.getBridgeSecret()) || properties.getBridgeSecret().length() < 32) {
            throw new IllegalStateException("项目桥接密钥未配置");
        }
        long kodUserId = kodUserId(tenantId, userId);
        return callAsKodUser(action, tenantId, userId, kodUserId, null, null, folderId);
    }

    /**
     * 统一执行 Java -> KodCloud 只读桥接调用。
     *
     * <p>普通项目请求由当前 OA 用户映射后的 KodCloud 身份执行；共享制度库请求使用
     * 管理员显式配置的服务账号。两种路径都只携带短期 HMAC 票据，绝不转发浏览器会话。</p>
     */
    private Map<String, Object> callAsKodUser(String action, Long tenantId, Long oaUserId, long kodUserId,
                                              Long projectId, Long fileId, Long folderId) {
        String ticket = issueTicket(tenantId, oaUserId, kodUserId);
        StringBuilder url = new StringBuilder(properties.getBridgeBaseUrl());
        url.append(properties.getBridgeBaseUrl().contains("?") ? "&" : "?")
                .append("agentAction=").append(action);
        if (projectId != null) url.append("&projectID=").append(projectId);
        if (fileId != null) url.append("&fileID=").append(fileId);
        if (folderId != null) url.append("&folderID=").append(folderId);
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-KodAgent-Bridge", ticket);
        headers.setAccept(java.util.Collections.singletonList(MediaType.APPLICATION_JSON));
        try {
            Map<?, ?> body = restTemplate.exchange(url.toString(), HttpMethod.GET,
                    new HttpEntity<>(headers), Map.class).getBody();
            if (body == null) throw new IllegalStateException("项目桥接返回为空");
            Object code = body.get("code");
            Object data = body.get("data");
            // KodCloud show_json 的成功码通常为 200；兼容 0/true 形式，拒绝其他错误响应。
            if (code != null && !("200".equals(String.valueOf(code)) || "0".equals(String.valueOf(code))
                    || Boolean.TRUE.equals(code))) {
                Object message = body.get("msg");
                throw new IllegalStateException(message == null ? "项目桥接失败" : String.valueOf(message));
            }
            if (!(data instanceof Map)) throw new IllegalStateException("项目桥接数据格式无效");
            @SuppressWarnings("unchecked") Map<String, Object> result = (Map<String, Object>) data;
            return result;
        } catch (RuntimeException ex) {
            if (ex.getMessage() != null && ex.getMessage().contains("KOD_USER_BINDING_REQUIRED")) throw ex;
            throw new IllegalStateException("项目数据服务暂不可用", ex);
        }
    }

    /** 从 PostgreSQL 读取有效的共享制度库绑定；未配置时返回明确的业务错误。 */
    private PolicyLibraryBinding policyLibraryBinding(Long tenantId) {
        if (tenantId == null) throw new IllegalArgumentException("制度库缺少租户编号");
        List<PolicyLibraryBinding> rows = jdbcTemplate.query(
                "SELECT kod_folder_id, kod_service_user_id FROM agent_policy_library_binding "
                        + "WHERE tenant_id=? AND status='ACTIVE'",
                (rs, rowNum) -> new PolicyLibraryBinding(rs.getLong("kod_folder_id"),
                        rs.getLong("kod_service_user_id")), tenantId);
        if (rows.isEmpty()) throw new IllegalStateException("POLICY_LIBRARY_NOT_CONFIGURED");
        return rows.get(0);
    }

    /** 将缺失的用户映射转换成 Agent 可识别的结构化业务错误，而不是 500。 */
    private static RuntimeException bindingRequired() {
        return ServiceExceptionUtil.exception0(409,
                "KOD_USER_BINDING_REQUIRED：当前 OA 用户尚未绑定 KodCloud 用户，请管理员先完成绑定");
    }

    private String issueTicket(Long tenantId, Long oaUserId, long kodUserId) {
        long expiresAt = System.currentTimeMillis() / 1000L + properties.getTicketTtlSeconds();
        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("purpose", "project.read");
        claims.put("tenantId", tenantId);
        claims.put("oaUserId", oaUserId);
        claims.put("userId", kodUserId);
        claims.put("expiresAt", expiresAt);
        claims.put("jti", UUID.randomUUID().toString());
        String encoded = encode(JsonUtils.toJsonString(claims).getBytes(StandardCharsets.UTF_8));
        try {
            Mac mac = Mac.getInstance(HMAC);
            mac.init(new SecretKeySpec(properties.getBridgeSecret().getBytes(StandardCharsets.UTF_8), HMAC));
            return encoded + "." + encode(mac.doFinal(encoded.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("项目桥接票据签发失败", ex);
        }
    }

    private static String encode(byte[] value) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    /** 共享制度库绑定的最小内部投影，避免把目录路径和凭据扩散到业务层。 */
    private static final class PolicyLibraryBinding {
        private final long kodFolderId;
        private final long kodServiceUserId;

        private PolicyLibraryBinding(long kodFolderId, long kodServiceUserId) {
            this.kodFolderId = kodFolderId;
            this.kodServiceUserId = kodServiceUserId;
        }
    }
}
