package cn.iocoder.yudao.server.service.agent;

import cn.hutool.crypto.SecureUtil;
import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.*;

/** Agent 模型供应商、模型同步和 Run 模型解析。 */
@Service
public class AgentModelService {

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    @Resource
    private RestTemplate restTemplate;

    /** The provider-key encryption key must be supplied by the environment. */
    @org.springframework.beans.factory.annotation.Value("${AGENT_MODEL_ENCRYPTION_KEY:${yudao.agent.models.encryption-key:}}")
    private String encryptionKey;

    public List<Map<String, Object>> listProviders(Long tenantId) {
        return jdbcTemplate.queryForList("SELECT id, name, provider_type, base_url, source, enabled, " +
                "(SELECT status FROM agent_model_credential c WHERE c.provider_id = p.id) credential_status " +
                "FROM agent_model_provider p WHERE tenant_id = ? AND deleted = FALSE ORDER BY id", tenantId);
    }

    public void deleteProvider(Long tenantId, Long providerId) {
        int updated = jdbcTemplate.update("UPDATE agent_model_provider SET deleted=TRUE, enabled=FALSE, updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?", providerId, tenantId);
        if (updated == 0) throw ServiceExceptionUtil.exception0(404, "供应商不存在");
    }

    public Map<String, Object> saveProvider(Long tenantId, Map<String, Object> request) {
        String name = required(request, "name");
        String baseUrl = required(request, "baseUrl").replaceAll("/+$", "");
        String apiKey = String.valueOf(request.getOrDefault("apiKey", "")).trim();
        Long id = request.get("id") == null ? null : Long.valueOf(String.valueOf(request.get("id")));
        if (id == null) {
            jdbcTemplate.update("INSERT INTO agent_model_provider(tenant_id,name,provider_type,base_url,source) VALUES(?,?,?,?,?)",
                    tenantId, name, request.getOrDefault("providerType", "OPENAI_COMPATIBLE"), baseUrl,
                    request.getOrDefault("source", "CUSTOM"));
            id = jdbcTemplate.queryForObject("SELECT id FROM agent_model_provider WHERE tenant_id=? AND name=?", Long.class, tenantId, name);
        } else {
            jdbcTemplate.update("UPDATE agent_model_provider SET name=?, provider_type=?, base_url=?, enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",
                    name, request.getOrDefault("providerType", "OPENAI_COMPATIBLE"), baseUrl,
                    request.getOrDefault("enabled", true), id, tenantId);
        }
        if (!apiKey.isEmpty()) {
            String encrypted = encrypt(apiKey);
            jdbcTemplate.update("INSERT INTO agent_model_credential(provider_id,api_key_ciphertext,status) VALUES(?,?, 'UNKNOWN') " +
                    "ON CONFLICT(provider_id) DO UPDATE SET api_key_ciphertext=EXCLUDED.api_key_ciphertext,status='UNKNOWN',updated_at=CURRENT_TIMESTAMP",
                    id, encrypted);
        }
        return jdbcTemplate.queryForMap("SELECT id, name, provider_type, base_url, source, enabled FROM agent_model_provider WHERE id=? AND tenant_id=?", id, tenantId);
    }

    public Map<String, Object> testProvider(Long tenantId, Long providerId) {
        ProviderConfig provider = provider(tenantId, providerId);
        String endpoint = provider.baseUrl + "/models";
        long startedAt = System.currentTimeMillis();
        try {
            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setBearerAuth(provider.apiKey);
            org.springframework.http.ResponseEntity<Map> entity = restTemplate.exchange(endpoint,
                    org.springframework.http.HttpMethod.GET, new org.springframework.http.HttpEntity<>(headers), Map.class);
            Map response = entity.getBody();
            if (response == null || !(response.get("data") instanceof List)) {
                String error = "接口响应缺少 data 模型数组";
                jdbcTemplate.update("UPDATE agent_model_credential SET status='INVALID',last_test_at=CURRENT_TIMESTAMP,last_error=? WHERE provider_id=?", error, providerId);
                return result(false, 0, error, endpoint, System.currentTimeMillis() - startedAt);
            }
            int count = ((List<?>) response.get("data")).size();
            jdbcTemplate.update("UPDATE agent_model_credential SET status='VALID',last_test_at=CURRENT_TIMESTAMP,last_error=NULL WHERE provider_id=?", providerId);
            return result(true, count, null, endpoint, System.currentTimeMillis() - startedAt);
        } catch (Exception ex) {
            jdbcTemplate.update("UPDATE agent_model_credential SET status='INVALID',last_test_at=CURRENT_TIMESTAMP,last_error=? WHERE provider_id=?", safeError(ex), providerId);
            return result(false, 0, safeError(ex), endpoint, System.currentTimeMillis() - startedAt);
        }
    }

    public Map<String, Object> syncModels(Long tenantId, Long providerId) {
        ProviderConfig provider = provider(tenantId, providerId);
        Map<String, Object> response;
        try {
            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setBearerAuth(provider.apiKey);
            org.springframework.http.ResponseEntity<Map> entity = restTemplate.exchange(provider.baseUrl + "/models",
                    org.springframework.http.HttpMethod.GET, new org.springframework.http.HttpEntity<>(headers), Map.class);
            response = entity.getBody();
        } catch (Exception ex) {
            throw ServiceExceptionUtil.exception0(502, "模型列表获取失败：" + safeError(ex));
        }
        Object data = response == null ? null : response.get("data");
        if (!(data instanceof List)) throw ServiceExceptionUtil.exception0(502, "供应商返回的模型列表格式无效");
        int count = 0;
        for (Object item : (List<?>) data) {
            if (!(item instanceof Map)) continue;
            Map itemMap = (Map) item;
            String modelName = String.valueOf(itemMap.getOrDefault("id", "")).trim();
            if (modelName.isEmpty()) continue;
            Map<String, Object> capabilities = new LinkedHashMap<>();
            capabilities.put("streaming", true);
            // OpenAI-compatible /models responses often omit capability data.
            // SiliconFlow must be conservative: models without an explicit
            // function-calling capability must not be advertised as Agent
            // models, otherwise the first tool call fails with provider 400.
            capabilities.put("tools", inferToolsCapability(provider, itemMap));
            capabilities.put("vision", modelName.toLowerCase().contains("vl") || modelName.toLowerCase().contains("vision"));
            // PostgreSQL does not implicitly cast a JDBC String parameter to jsonb.
            // Without the explicit cast the provider request succeeds, but the
            // first model insert fails and the UI receives a generic 500.
            jdbcTemplate.update("INSERT INTO agent_model(provider_id,model_name,display_name,capabilities,last_synced_at) VALUES(?,?,?,?::jsonb,CURRENT_TIMESTAMP) " +
                            "ON CONFLICT(provider_id,model_name) DO UPDATE SET display_name=EXCLUDED.display_name,capabilities=EXCLUDED.capabilities,last_synced_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP",
                    providerId, modelName, modelName, JsonUtils.toJsonString(capabilities));
            count++;
        }
        return result(true, count, null, provider.baseUrl + "/models", null);
    }

    public List<Map<String, Object>> listModels(Long tenantId, Long providerId) {
        // Agent models must support the two capabilities required by the
        // runtime: streamed output and function/tool calling. Models without
        // either capability are ordinary chat models and must not leak into
        // Agent model pickers or default-binding configuration.
        String capabilityFilter = " AND m.capabilities->>'streaming'='true' AND m.capabilities->>'tools'='true'";
        if (providerId == null) return jdbcTemplate.queryForList("SELECT m.id,m.provider_id,p.name provider_name,m.model_name,m.display_name,m.capabilities::text capabilities,m.enabled FROM agent_model m JOIN agent_model_provider p ON p.id=m.provider_id WHERE p.tenant_id=? AND p.enabled=true AND p.deleted=false AND m.enabled=true" + capabilityFilter + " ORDER BY p.id,m.model_name", tenantId);
        return jdbcTemplate.queryForList("SELECT m.id,m.provider_id,p.name provider_name,m.model_name,m.display_name,m.capabilities::text capabilities,m.enabled FROM agent_model m JOIN agent_model_provider p ON p.id=m.provider_id WHERE p.tenant_id=? AND p.id=? AND p.enabled=true AND p.deleted=false AND m.enabled=true" + capabilityFilter + " ORDER BY m.model_name", tenantId, providerId);
    }

    /** 查询当前租户的模型绑定，API Key 永不出现在返回值中。 */
    public List<Map<String, Object>> listBindings(Long tenantId) {
        return jdbcTemplate.queryForList("SELECT b.id,b.tenant_id,b.user_id,b.agent_name,b.model_id,b.enabled, " +
                "m.model_name,m.display_name,p.name provider_name " +
                "FROM agent_model_binding b JOIN agent_model m ON m.id=b.model_id " +
                "JOIN agent_model_provider p ON p.id=m.provider_id " +
                "WHERE b.tenant_id=? AND p.enabled=true AND p.deleted=false AND m.enabled=true AND m.capabilities->>'streaming'='true' AND m.capabilities->>'tools'='true' ORDER BY b.user_id NULLS FIRST,b.agent_name", tenantId);
    }

    /** 保存用户、租户或 Agent 的默认模型绑定。 */
    @org.springframework.transaction.annotation.Transactional
    public Map<String, Object> saveBinding(Long tenantId, Map<String, Object> request) {
        String agentName = String.valueOf(request.getOrDefault("agentName", "oa-main-agent")).trim();
        if (agentName.isEmpty()) agentName = "oa-main-agent";
        Long userId = nullableLong(request.get("userId"));
        Long modelId = nullableLong(request.get("modelId"));
        if (modelId == null) throw ServiceExceptionUtil.exception0(400, "modelId 不能为空");
        if (!modelBelongsToTenant(tenantId, modelId)) throw ServiceExceptionUtil.exception0(400, "模型不存在或不属于当前租户");
        if (!agentCapabilitiesSupported(tenantId, modelId)) {
            throw ServiceExceptionUtil.exception0(400, "该模型不满足 Agent 所需的流式输出和工具调用能力");
        }
        jdbcTemplate.update("DELETE FROM agent_model_binding WHERE tenant_id=? AND user_id IS NOT DISTINCT FROM ? AND agent_name=?", tenantId, userId, agentName);
        jdbcTemplate.update("INSERT INTO agent_model_binding(tenant_id,user_id,agent_name,model_id,enabled) VALUES(?,?,?,?,?)",
                tenantId, userId, agentName, modelId, request.getOrDefault("enabled", true));
        return jdbcTemplate.queryForMap("SELECT b.id,b.tenant_id,b.user_id,b.agent_name,b.model_id,b.enabled,m.model_name,m.display_name,p.name provider_name " +
                "FROM agent_model_binding b JOIN agent_model m ON m.id=b.model_id JOIN agent_model_provider p ON p.id=m.provider_id " +
                "WHERE b.tenant_id=? AND b.user_id IS NOT DISTINCT FROM ? AND b.agent_name=?", tenantId, userId, agentName);
    }

    public void deleteBinding(Long tenantId, Long bindingId) {
        int count = jdbcTemplate.update("DELETE FROM agent_model_binding WHERE id=? AND tenant_id=?", bindingId, tenantId);
        if (count == 0) throw ServiceExceptionUtil.exception0(404, "模型绑定不存在");
    }

    /** 管理员可修正供应商无法可靠探测的能力。 */
    public Map<String, Object> updateCapabilities(Long tenantId, Long modelId, Map<String, Object> capabilities) {
        if (!modelBelongsToTenant(tenantId, modelId)) throw ServiceExceptionUtil.exception0(404, "模型不存在或不属于当前租户");
        jdbcTemplate.update("UPDATE agent_model SET capabilities=?::jsonb,updated_at=CURRENT_TIMESTAMP WHERE id=?", JsonUtils.toJsonString(capabilities), modelId);
        return jdbcTemplate.queryForMap("SELECT id,provider_id,model_name,display_name,capabilities,enabled FROM agent_model WHERE id=?", modelId);
    }

    private boolean agentCapabilitiesSupported(Long tenantId, Long modelId) {
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM agent_model m JOIN agent_model_provider p ON p.id=m.provider_id " +
                "WHERE m.id=? AND p.tenant_id=? AND m.enabled=true AND p.enabled=true AND p.deleted=false " +
                "AND m.capabilities->>'streaming'='true' AND m.capabilities->>'tools'='true'", Integer.class, modelId, tenantId);
        return count != null && count > 0;
    }

    /** 显式模型优先，否则按用户+Agent、用户默认、租户+Agent、租户默认解析。 */
    public Map<String, Object> resolveForRun(Long tenantId, Long userId, Long modelId, String agentName) {
        if (modelId != null) return resolve(tenantId, userId, modelId);
        String name = agentName == null || agentName.trim().isEmpty() ? "oa-main-agent" : agentName.trim();
        Long selected = null;
        List<Map<String, Object>> rows = jdbcTemplate.queryForList("SELECT model_id FROM agent_model_binding " +
                "WHERE tenant_id=? AND enabled=true AND ((user_id=? AND agent_name=?) OR (user_id=? AND agent_name='*') OR " +
                "(user_id IS NULL AND agent_name=?) OR (user_id IS NULL AND agent_name='*')) " +
                "ORDER BY CASE WHEN user_id=? AND agent_name=? THEN 1 WHEN user_id=? AND agent_name='*' THEN 2 " +
                "WHEN user_id IS NULL AND agent_name=? THEN 3 ELSE 4 END LIMIT 1",
                tenantId, userId, name, userId, name, userId, name, userId, name);
        if (!rows.isEmpty()) selected = ((Number) rows.get(0).get("model_id")).longValue();
        if (selected == null) throw ServiceExceptionUtil.exception0(404, "尚未配置可用的默认模型");
        return resolve(tenantId, userId, selected);
    }

    /** Python Agent 使用：按显式 modelId 解析本次 Run 的模型配置。 */
    public Map<String, Object> resolve(Long tenantId, Long userId, Long modelId) {
        String sql = "SELECT m.id model_id,m.model_name,m.capabilities,p.id provider_id,p.name provider_name,p.base_url,c.api_key_ciphertext " +
                "FROM agent_model m JOIN agent_model_provider p ON p.id=m.provider_id JOIN agent_model_credential c ON c.provider_id=p.id " +
                "WHERE m.id=? AND p.tenant_id=? AND p.enabled=true AND m.enabled=true";
        Map<String, Object> row;
        try { row = jdbcTemplate.queryForMap(sql, modelId, tenantId); }
        catch (Exception ex) { throw ServiceExceptionUtil.exception0(404, "模型不存在或未启用"); }
        if (!toolsSupported(row.get("capabilities")) || !streamingSupported(row.get("capabilities"))) {
            throw ServiceExceptionUtil.exception0(400, "当前模型不满足 Agent 所需的流式输出和工具调用能力，请切换模型");
        }
        row.put("apiKey", decrypt(String.valueOf(row.remove("api_key_ciphertext"))));
        return row;
    }

    @SuppressWarnings("rawtypes")
    private boolean inferToolsCapability(ProviderConfig provider, Map item) {
        String modelName = String.valueOf(item.getOrDefault("id", "")).toLowerCase(Locale.ROOT);
        Object explicit = firstNonNull(item.get("tools"), item.get("tool_calling"),
                item.get("function_calling"), item.get("supports_tools"));
        if (explicit instanceof Boolean) return (Boolean) explicit;
        String endpoint = provider.baseUrl.toLowerCase(Locale.ROOT);
        // SiliconFlow's /models response does not reliably expose capability
        // flags. Do not disable every model by provider name. Only obvious
        // embedding, reranking, media and non-chat models are excluded; chat
        // and coding models remain available and the runtime remains the
        // final authority when a provider rejects a tool call.
        if (endpoint.contains("siliconflow")) return !looksLikeNonChatModel(modelName);
        return true;
    }

    private boolean looksLikeNonChatModel(String modelName) {
        return modelName.contains("embedding") || modelName.contains("reranker") ||
                modelName.contains("bge-") || modelName.contains("ocr") ||
                modelName.contains("speech") || modelName.contains("audio") ||
                modelName.contains("tts") || modelName.contains("kolors") ||
                modelName.contains("z-image") || modelName.contains("image-edit") ||
                modelName.contains("wan2") || modelName.contains("captioner");
    }

    private Object firstNonNull(Object... values) {
        for (Object value : values) if (value != null) return value;
        return null;
    }

    private boolean toolsSupported(Object capabilities) {
        if (capabilities == null) return true;
        String value = String.valueOf(capabilities).replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
        return !value.contains("\"tools\":false") && !value.contains("\"tool_calling\":false");
    }

    private boolean streamingSupported(Object capabilities) {
        if (capabilities == null) return true;
        String value = String.valueOf(capabilities).replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
        return !value.contains("\"streaming\":false");
    }

    private ProviderConfig provider(Long tenantId, Long providerId) {
        Map<String, Object> row;
        try { row = jdbcTemplate.queryForMap("SELECT p.id,p.base_url,c.api_key_ciphertext FROM agent_model_provider p JOIN agent_model_credential c ON c.provider_id=p.id WHERE p.id=? AND p.tenant_id=? AND p.enabled=true", providerId, tenantId); }
        catch (Exception ex) { throw ServiceExceptionUtil.exception0(404, "供应商不存在、未启用或未配置 API Key"); }
        return new ProviderConfig(String.valueOf(row.get("base_url")), decrypt(String.valueOf(row.get("api_key_ciphertext"))));
    }

    private boolean modelBelongsToTenant(Long tenantId, Long modelId) {
        Integer count = jdbcTemplate.queryForObject("SELECT COUNT(1) FROM agent_model m JOIN agent_model_provider p ON p.id=m.provider_id " +
                "WHERE m.id=? AND p.tenant_id=? AND p.deleted=false", Integer.class, modelId, tenantId);
        return count != null && count > 0;
    }

    private Long nullableLong(Object value) {
        if (value == null || String.valueOf(value).trim().isEmpty() || "null".equalsIgnoreCase(String.valueOf(value))) return null;
        return Long.valueOf(String.valueOf(value));
    }

    private String required(Map<String, Object> request, String field) {
        String value = String.valueOf(request.getOrDefault(field, "")).trim();
        if (value.isEmpty()) throw ServiceExceptionUtil.exception0(400, field + " 不能为空");
        return value;
    }

    private String encrypt(String value) { return SecureUtil.aes(requireEncryptionKey()).encryptBase64(value); }
    private String decrypt(String value) { return SecureUtil.aes(requireEncryptionKey()).decryptStr(value); }
    private byte[] requireEncryptionKey() {
        String value = encryptionKey == null ? "" : encryptionKey.trim();
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (!(bytes.length == 16 || bytes.length == 24 || bytes.length == 32)) {
            throw ServiceExceptionUtil.exception0(500,
                    "Agent 模型加密密钥未配置或长度无效，必须为 16、24 或 32 字节");
        }
        return bytes;
    }
    private String safeError(Exception ex) { return String.valueOf(ex.getMessage()).replaceAll("(?i)(api[_-]?key|authorization|bearer)\\s*[:=]?\\s*\\S+", "$1=***").substring(0, Math.min(900, String.valueOf(ex.getMessage()).length())); }
    private Map<String, Object> result(boolean success, int count, String error, String endpoint, Long latencyMs) {
        Map<String,Object> result = new LinkedHashMap<>();
        result.put("success", success);
        result.put("count", count);
        result.put("endpoint", endpoint);
        if (latencyMs != null) result.put("latencyMs", latencyMs);
        if (error != null) result.put("error", error);
        return result;
    }
    private static final class ProviderConfig {
        private final String baseUrl;
        private final String apiKey;

        private ProviderConfig(String baseUrl, String apiKey) {
            this.baseUrl = baseUrl;
            this.apiKey = apiKey;
        }
    }
}
