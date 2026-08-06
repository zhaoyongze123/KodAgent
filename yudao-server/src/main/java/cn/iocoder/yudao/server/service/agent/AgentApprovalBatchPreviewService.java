package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.ApprovalBatchExecuteResponse;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Durable confirmation and idempotency boundary for batch approval actions.
 *
 * <p>The BPM transaction itself remains in MySQL. This service intentionally
 * contains only the short-lived preview/confirmation fact in the Agent event
 * store, so a model cannot turn an old result card into a write request.</p>
 */
@Service
public class AgentApprovalBatchPreviewService {

    private static final int PREVIEW_TTL_MINUTES = 15;

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    @Transactional(transactionManager = "agentEventTransactionManager")
    public StoredPreview create(Long tenantId, Long userId, String action, String reason,
                                String previewMessageId, String runId, String threadId, String operationId,
                                List<Map<String, Object>> tasks) {
        if (tasks == null || tasks.isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_EMPTY：没有可确认的待办审批");
        }
        validateLength(operationId, "operationId");
        StoredPreview existing = reuseExisting(tenantId, userId, operationId, action, reason);
        if (existing != null) {
            return existing;
        }
        String previewId = UUID.randomUUID().toString();
        String token = UUID.randomUUID().toString();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("action", action);
        data.put("reason", reason);
        data.put("tasks", tasks);
        data.put("taskIds", tasks.stream().map(item -> String.valueOf(item.get("taskId")))
                .collect(java.util.stream.Collectors.toList()));
        List<String> inserted = jdbcTemplate.query("INSERT INTO agent_approval_batch_preview "
                        + "(preview_id, tenant_id, owner_user_id, preview_message_id, run_id, thread_id, operation_id, confirmation_token, "
                        + "status, preview_data, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', CAST(? AS jsonb), "
                        + "CURRENT_TIMESTAMP + INTERVAL '15 minutes') ON CONFLICT DO NOTHING RETURNING preview_id",
                (rs, rowNum) -> rs.getString("preview_id"),
                previewId, tenantId, userId, previewMessageId, nullable(runId), nullable(threadId), operationId, token,
                JsonUtils.toJsonString(data));
        if (inserted.isEmpty()) {
            StoredPreview concurrent = reuseExisting(tenantId, userId, operationId, action, reason);
            if (concurrent != null) {
                return concurrent;
            }
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BATCH_OPERATION_CONFLICT：Operation 已被其他批量预览占用");
        }
        return new StoredPreview(previewId, operationId, token, action, reason, tasks,
                LocalDateTime.now().plusMinutes(PREVIEW_TTL_MINUTES));
    }

    /**
     * Read the durable, user-scoped preview that backs a batch ApprovalCard.
     * The opaque confirmation token is intentionally returned only to the
     * trusted Agent runtime, never to the browser decision endpoint.
     */
    public Map<String, Object> get(Long tenantId, Long userId, String previewId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT preview_id, operation_id, preview_message_id, run_id, thread_id, confirmation_token, status, idempotency_key, "
                        + "preview_data::text, result_data::text, expires_at, decision_idempotency_key, rejected_reason "
                        + "FROM agent_approval_batch_preview WHERE preview_id = ? AND tenant_id = ? AND owner_user_id = ?",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("previewId", rs.getString("preview_id"));
                    row.put("operationId", rs.getString("operation_id"));
                    row.put("messageId", rs.getString("preview_message_id"));
                    row.put("runId", rs.getString("run_id"));
                    row.put("threadId", rs.getString("thread_id"));
                    row.put("confirmationToken", rs.getString("confirmation_token"));
                    row.put("status", rs.getString("status"));
                    row.put("idempotencyKey", rs.getString("idempotency_key"));
                    row.put("preview", JsonUtils.parseObject(rs.getString("preview_data"), Map.class));
                    String result = rs.getString("result_data");
                    row.put("result", result == null ? null : JsonUtils.parseObject(result, Map.class));
                    Timestamp expiresAt = rs.getTimestamp("expires_at");
                    row.put("expiresAt", expiresAt == null ? null : expiresAt.toLocalDateTime());
                    row.put("decisionIdempotencyKey", rs.getString("decision_idempotency_key"));
                    row.put("rejectedReason", rs.getString("rejected_reason"));
                    return row;
                }, previewId, tenantId, userId);
        if (rows.isEmpty()) {
            throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_BATCH_NOT_FOUND：批量审批预览不存在或无权访问");
        }
        Map<String, Object> result = rows.get(0);
        LocalDateTime expiresAt = (LocalDateTime) result.get("expiresAt");
        if (("PENDING".equals(result.get("status")) || "APPROVED".equals(result.get("status")))
                && (expiresAt == null || !expiresAt.isAfter(LocalDateTime.now()))) {
            jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
                    + "WHERE preview_id = ? AND tenant_id = ? AND owner_user_id = ? AND status IN ('PENDING', 'APPROVED')", previewId, tenantId, userId);
            result.put("status", "EXPIRED");
        }
        return result;
    }

    /** Persist the user's one official ApprovalCard decision before LangGraph resumes. */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> decide(Long tenantId, Long userId, String previewId, String decision,
                                      String idempotencyKey, String rejectReason) {
        validateLength(idempotencyKey, "decisionIdempotencyKey");
        if (!"APPROVE".equals(decision) && !"REJECT".equals(decision)) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_INVALID：不支持的确认动作");
        }
        String target = "APPROVE".equals(decision) ? "APPROVED" : "REJECTED";
        int updated = jdbcTemplate.update(
                "UPDATE agent_approval_batch_preview SET status = ?, decision_idempotency_key = ?, "
                        + "approved_at = CASE WHEN ? = 'APPROVED' THEN CURRENT_TIMESTAMP ELSE approved_at END, "
                        + "rejected_at = CASE WHEN ? = 'REJECTED' THEN CURRENT_TIMESTAMP ELSE rejected_at END, "
                        + "rejected_reason = CASE WHEN ? = 'REJECTED' THEN ? ELSE rejected_reason END, updated_at = CURRENT_TIMESTAMP "
                        + "WHERE preview_id = ? AND tenant_id = ? AND owner_user_id = ? AND status = 'PENDING' "
                        + "AND expires_at > CURRENT_TIMESTAMP",
                target, idempotencyKey, target, target, target, rejectReason, previewId, tenantId, userId);
        if (updated == 0) {
            Map<String, Object> existing = get(tenantId, userId, previewId);
            if (target.equals(existing.get("status")) && idempotencyKey.equals(existing.get("decisionIdempotencyKey"))) {
                return existing;
            }
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_STATE_MISMATCH：批量审批当前状态为 " + existing.get("status"));
        }
        return get(tenantId, userId, previewId);
    }

    /** Claim one pending preview before opening the MySQL all-or-nothing BPM transaction. */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public BatchClaim claim(Long tenantId, Long userId, String previewId, String token,
                            String operationId, String idempotencyKey, String confirmationMessageId) {
        validateLength(idempotencyKey, "idempotencyKey");
        validateLength(operationId, "operationId");
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, operation_id, confirmation_token, preview_message_id, idempotency_key, expires_at, preview_data::text, result_data::text "
                        + "FROM agent_approval_batch_preview WHERE preview_id = ? AND tenant_id = ? AND owner_user_id = ?",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("operationId", rs.getString("operation_id"));
                    row.put("confirmationToken", rs.getString("confirmation_token"));
                    row.put("previewMessageId", rs.getString("preview_message_id"));
                    row.put("idempotencyKey", rs.getString("idempotency_key"));
                    Timestamp expiresAt = rs.getTimestamp("expires_at");
                    row.put("expiresAt", expiresAt == null ? null : expiresAt.toLocalDateTime());
                    row.put("preview", JsonUtils.parseObject(rs.getString("preview_data"), Map.class));
                    String result = rs.getString("result_data");
                    row.put("result", result == null ? null : JsonUtils.parseObject(result, ApprovalBatchExecuteResponse.class));
                    return row;
                }, previewId, tenantId, userId);
        if (rows.isEmpty()) {
            throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_BATCH_NOT_FOUND：批量审批预览不存在或无权访问");
        }
        Map<String, Object> row = rows.get(0);
        if (!token.equals(row.get("confirmationToken"))) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_TOKEN_INVALID：确认令牌无效");
        }
        if (!operationId.equals(row.get("operationId"))) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_OPERATION_MISMATCH：批量审批与当前 Operation 不匹配");
        }
        String status = String.valueOf(row.get("status"));
        if ("COMPLETED".equals(status) && idempotencyKey.equals(row.get("idempotencyKey"))) {
            return BatchClaim.replay((ApprovalBatchExecuteResponse) row.get("result"));
        }
        if (!"APPROVED".equals(status)) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_STATE_MISMATCH：批量审批当前状态为 " + status);
        }
        LocalDateTime expiresAt = (LocalDateTime) row.get("expiresAt");
        if (expiresAt == null || !expiresAt.isAfter(LocalDateTime.now())) {
            jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE preview_id = ? AND tenant_id = ? AND owner_user_id = ? AND status IN ('PENDING', 'APPROVED')", previewId, tenantId, userId);
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_EXPIRED：批量审批预览已过期，请重新筛选");
        }
        int claimed = jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'EXECUTING', idempotency_key = ?, "
                        + "confirmation_message_id = ?, updated_at = CURRENT_TIMESTAMP WHERE preview_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'APPROVED' AND expires_at > CURRENT_TIMESTAMP",
                idempotencyKey, confirmationMessageId, previewId, tenantId, userId);
        if (claimed != 1) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_CONFLICT：批量审批正在处理或状态已改变");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> preview = (Map<String, Object>) row.get("preview");
        return BatchClaim.claimed(preview);
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public void complete(Long tenantId, Long userId, String previewId, String idempotencyKey,
                         ApprovalBatchExecuteResponse response) {
        int updated = jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'COMPLETED', result_data = CAST(? AS jsonb), "
                        + "completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE preview_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'EXECUTING' AND idempotency_key = ?",
                JsonUtils.toJsonString(response), previewId, tenantId, userId, idempotencyKey);
        if (updated != 1) {
            Map<String, Object> current = get(tenantId, userId, previewId);
            if ("COMPLETED".equals(current.get("status"))
                    && idempotencyKey.equals(current.get("idempotencyKey"))) {
                return;
            }
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_CONFLICT：批量审批确认状态已改变");
        }
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public void fail(Long tenantId, Long userId, String previewId, String idempotencyKey,
                     ApprovalBatchExecuteResponse response) {
        int updated = jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'FAILED', result_data = CAST(? AS jsonb), "
                        + "updated_at = CURRENT_TIMESTAMP WHERE preview_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'EXECUTING' AND idempotency_key = ?",
                JsonUtils.toJsonString(response), previewId, tenantId, userId, idempotencyKey);
        if (updated != 1) {
            Map<String, Object> current = get(tenantId, userId, previewId);
            if ("FAILED".equals(current.get("status"))
                    && idempotencyKey.equals(current.get("idempotencyKey"))) {
                return;
            }
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_CONFLICT：批量审批确认状态已改变");
        }
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public void release(Long tenantId, Long userId, String previewId, String idempotencyKey) {
        jdbcTemplate.update("UPDATE agent_approval_batch_preview SET status = 'APPROVED', idempotency_key = NULL, "
                        + "confirmation_message_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE preview_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'EXECUTING' AND idempotency_key = ?",
                previewId, tenantId, userId, idempotencyKey);
    }

    private void validateLength(String value, String name) {
        if (value == null || value.trim().isEmpty() || value.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_INVALID：" + name + " 无效");
        }
    }

    private String findExistingPreviewId(Long tenantId, Long userId, String operationId) {
        List<String> ids = jdbcTemplate.query(
                "SELECT preview_id FROM agent_approval_batch_preview "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND operation_id = ?",
                (rs, rowNum) -> rs.getString("preview_id"), tenantId, userId, operationId);
        return ids.isEmpty() ? null : ids.get(0);
    }

    private StoredPreview reuseExisting(Long tenantId, Long userId, String operationId,
                                        String action, String reason) {
        String existingId = findExistingPreviewId(tenantId, userId, operationId);
        if (existingId == null) {
            return null;
        }
        Map<String, Object> existing = get(tenantId, userId, existingId);
        Map<?, ?> existingPreview = existing.get("preview") instanceof Map
                ? (Map<?, ?>) existing.get("preview") : java.util.Collections.emptyMap();
        String existingAction = String.valueOf(existingPreview.containsKey("action")
                ? existingPreview.get("action") : "");
        String existingReason = String.valueOf(existingPreview.containsKey("reason")
                ? existingPreview.get("reason") : "");
        if (!action.equals(existingAction) || !reason.equals(existingReason)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BATCH_OPERATION_CONFLICT：Operation 已绑定其他批量预览");
        }
        return StoredPreview.from(existing);
    }

    private String nullable(String value) {
        return value == null || value.trim().isEmpty() ? null : value.trim();
    }

    public static final class StoredPreview {
        private final String previewId;
        private final String operationId;
        private final String confirmationToken;
        private final String action;
        private final String reason;
        private final List<Map<String, Object>> tasks;
        private final LocalDateTime expiresAt;

        public StoredPreview(String previewId, String operationId, String confirmationToken, String action, String reason,
                             List<Map<String, Object>> tasks, LocalDateTime expiresAt) {
            this.previewId = previewId; this.operationId = operationId; this.confirmationToken = confirmationToken; this.action = action;
            this.reason = reason; this.tasks = tasks; this.expiresAt = expiresAt;
        }
        @SuppressWarnings("unchecked")
        public static StoredPreview from(Map<String, Object> row) {
            Map<String, Object> preview = row.get("preview") instanceof Map
                    ? (Map<String, Object>) row.get("preview") : new LinkedHashMap<>();
            Object tasks = preview.get("tasks");
            List<Map<String, Object>> taskList = tasks instanceof List
                    ? (List<Map<String, Object>>) tasks : java.util.Collections.emptyList();
            return new StoredPreview(String.valueOf(row.get("previewId")),
                    String.valueOf(row.get("operationId") == null ? "" : row.get("operationId")),
                    String.valueOf(row.get("confirmationToken") == null ? "" : row.get("confirmationToken")),
                    String.valueOf(preview.getOrDefault("action", "")),
                    String.valueOf(preview.getOrDefault("reason", "")), taskList,
                    (LocalDateTime) row.get("expiresAt"));
        }
        public String getPreviewId() { return previewId; }
        public String getOperationId() { return operationId; }
        public String getConfirmationToken() { return confirmationToken; }
        public String getAction() { return action; }
        public String getReason() { return reason; }
        public List<Map<String, Object>> getTasks() { return tasks; }
        public LocalDateTime getExpiresAt() { return expiresAt; }
    }

    public static final class BatchClaim {
        private final boolean replay;
        private final Map<String, Object> preview;
        private final ApprovalBatchExecuteResponse replayResponse;
        private BatchClaim(boolean replay, Map<String, Object> preview, ApprovalBatchExecuteResponse replayResponse) {
            this.replay = replay; this.preview = preview; this.replayResponse = replayResponse;
        }
        public static BatchClaim claimed(Map<String, Object> preview) { return new BatchClaim(false, preview, null); }
        public static BatchClaim replay(ApprovalBatchExecuteResponse response) { return new BatchClaim(true, null, response); }
        public boolean isReplay() { return replay; }
        public Map<String, Object> getPreview() { return preview; }
        public ApprovalBatchExecuteResponse getReplayResponse() { return replayResponse; }
    }
}
