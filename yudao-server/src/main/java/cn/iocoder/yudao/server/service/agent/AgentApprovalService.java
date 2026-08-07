package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.util.LinkedHashMap;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Agent Human-in-the-loop 审批事实状态。
 *
 * <p>审批数据必须按 tenant/user/run/thread/message/task 绑定读取，前端不需要再
 * 扫描整段事件历史拼卡片。状态变更使用条件更新和幂等键，重复点击不会重复推进状态。</p>
 */
@Service
public class AgentApprovalService {

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    /** Create a meeting approval bound to the durable Python Operation. */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public String create(Long tenantId, Long userId, String runId, String threadId,
                         String messageId, String taskId, String draftId, String operationId) {
        String validRunId = requiredBinding(runId, "runId");
        String validThreadId = requiredBinding(threadId, "threadId");
        String validMessageId = requiredBinding(messageId, "messageId");
        if (draftId == null || draftId.trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BINDING_INVALID：draftId 不能为空");
        }
        String validOperationId = requiredBinding(operationId, "operationId");
        validateDraftBinding(tenantId, userId, validRunId, validThreadId, validMessageId, draftId, validOperationId);
        String existingSql = "SELECT approval_id FROM agent_approval WHERE tenant_id = ? AND approver_user_id = ? "
                + "AND draft_id = ? AND run_id = ? AND thread_id = ? AND message_id = ? "
                + "AND operation_id = ? AND status = 'PENDING' AND expires_at > CURRENT_TIMESTAMP";
        List<String> existing = jdbcTemplate.query(existingSql,
                (rs, rowNum) -> rs.getString("approval_id"),
                tenantId, userId, draftId, validRunId, validThreadId, validMessageId, validOperationId);
        if (!existing.isEmpty()) return existing.get(0);

        String approvalId = UUID.randomUUID().toString();
        try {
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, task_id, "
                            + "operation_id, draft_id, status, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', "
                            + "CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                    approvalId, tenantId, userId, validRunId, validThreadId, validMessageId, taskId,
                    validOperationId, draftId);
            return approvalId;
        } catch (RuntimeException ex) {
            String concurrentSql = "SELECT approval_id FROM agent_approval WHERE tenant_id = ? AND approver_user_id = ? "
                            + "AND draft_id = ? AND run_id = ? AND thread_id = ? AND message_id = ? "
                            + "AND operation_id = ? AND status = 'PENDING' ORDER BY created_at DESC LIMIT 1";
            List<String> concurrent = jdbcTemplate.query(concurrentSql,
                    (rs, rowNum) -> rs.getString("approval_id"),
                    tenantId, userId, draftId, validRunId, validThreadId, validMessageId, validOperationId);
            if (!concurrent.isEmpty()) return concurrent.get(0);
            throw ex;
        }
    }

    /** Create a generic approval and bind it to one durable Agent Operation. */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public String createGeneric(Long tenantId, Long userId, String runId, String threadId,
                                String messageId, String taskId, String draftId,
                                String draftType, Map<String, Object> draftData,
                                String operationId) {
        String validRunId = requiredBinding(runId, "runId");
        String validThreadId = requiredBinding(threadId, "threadId");
        String validMessageId = requiredBinding(messageId, "messageId");
        if (draftId == null || draftId.trim().isEmpty() || draftType == null || draftType.trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BINDING_INVALID：通用审批草稿字段不能为空");
        }
        String validOperationId = requiredBinding(operationId, "operationId");
        List<Map<String, Object>> existing = jdbcTemplate.query(
                "SELECT approval_id, operation_id FROM agent_approval WHERE tenant_id = ? AND approver_user_id = ? "
                        + "AND draft_id = ? AND run_id = ? AND thread_id = ? AND message_id = ? "
                        + "AND operation_id = ? "
                        + "ORDER BY created_at DESC LIMIT 1",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("approvalId", rs.getString("approval_id"));
                    row.put("operationId", rs.getString("operation_id"));
                    return row;
                }, tenantId, userId, draftId,
                validRunId, validThreadId, validMessageId, validOperationId);
        if (!existing.isEmpty()) {
            String existingOperationId = (String) existing.get(0).get("operationId");
            if (!validOperationId.equals(existingOperationId)) {
                throw ServiceExceptionUtil.exception0(409,
                        "AGENT_APPROVAL_OPERATION_MISMATCH：草稿已绑定其他 Operation");
            }
            return String.valueOf(existing.get(0).get("approvalId"));
        }
        String approvalId = UUID.randomUUID().toString();
        try {
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, task_id, operation_id, draft_id, draft_type, draft_data, status, expires_at) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), 'PENDING', CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                approvalId, tenantId, userId, validRunId, validThreadId, validMessageId, taskId,
                    validOperationId, draftId, draftType,
                    JsonUtils.toJsonString(draftData == null ? new LinkedHashMap<>() : draftData));
            return approvalId;
        } catch (RuntimeException ex) {
            List<Map<String, Object>> concurrent = jdbcTemplate.query(
                    "SELECT approval_id, operation_id FROM agent_approval WHERE tenant_id = ? AND approver_user_id = ? "
                            + "AND draft_id = ? AND run_id = ? AND thread_id = ? AND message_id = ? "
                            + "AND operation_id = ? "
                            + "ORDER BY created_at DESC LIMIT 1",
                    (rs, rowNum) -> {
                        Map<String, Object> row = new LinkedHashMap<>();
                        row.put("approvalId", rs.getString("approval_id"));
                        row.put("operationId", rs.getString("operation_id"));
                        return row;
                    }, tenantId, userId, draftId, validRunId, validThreadId, validMessageId, validOperationId);
            if (!concurrent.isEmpty()) {
                String existingOperationId = (String) concurrent.get(0).get("operationId");
                if (!validOperationId.equals(existingOperationId)) {
                    throw ServiceExceptionUtil.exception0(409,
                            "AGENT_APPROVAL_OPERATION_MISMATCH：草稿已绑定其他 Operation");
                }
                return String.valueOf(concurrent.get(0).get("approvalId"));
            }
            throw ex;
        }
    }

    public Map<String, Object> get(Long tenantId, Long userId, String approvalId) {
        expireIfNeeded(tenantId, userId, approvalId);
        return findApproval(tenantId, userId, approvalId, false);
    }

    /** 精确读取当前 PENDING 审批和审批卡片，不扫描事件历史。 */
    public Map<String, Object> getPendingCard(Long tenantId, Long userId, String approvalId) {
        expireIfNeeded(tenantId, userId, approvalId);
        return findApproval(tenantId, userId, approvalId, true);
    }

    /** 通过草稿精确读取对应审批，避免跨 Run/跨轮次取到旧卡片。 */
    public Map<String, Object> getPendingCardByDraft(Long tenantId, Long userId, String draftId) {
        expireIfNeededByDraft(tenantId, userId, draftId);
        List<Map<String, Object>> rows = jdbcTemplate.query(
                approvalSelect() + " FROM agent_approval a "
                        + "LEFT JOIN agent_meeting_booking_draft d ON d.approval_id = a.approval_id "
                        + "LEFT JOIN agent_personal_schedule_draft s ON s.approval_id = a.approval_id "
                        + "LEFT JOIN agent_party_file_draft p ON p.approval_id = a.approval_id "
                + "WHERE a.tenant_id = ? AND a.approver_user_id = ? AND a.draft_id = ? "
                + "AND a.archived_at IS NULL AND a.status = 'PENDING' AND a.expires_at > CURRENT_TIMESTAMP "
                + "AND ((d.draft_id IS NOT NULL AND d.archived_at IS NULL AND a.message_id = d.message_id) "
                + "OR (s.draft_id IS NOT NULL AND s.archived_at IS NULL AND a.message_id = s.message_id) "
                + "OR (p.draft_id IS NOT NULL AND p.archived_at IS NULL AND a.message_id = p.message_id)) "
                + "AND a.message_id IS NOT NULL",
                (rs, rowNum) -> mapApproval(rs), tenantId, userId, draftId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_PENDING_NOT_FOUND：当前草稿没有待处理审批");
        return card(rows.get(0));
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> approve(Long tenantId, Long userId, String approvalId,
                                       String idempotencyKey) {
        validateKey(idempotencyKey);
        int updated = jdbcTemplate.update("UPDATE agent_approval SET status = 'APPROVED', "
                        + "idempotency_key = ?, approved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
                        + "WHERE approval_id = ? AND tenant_id = ? AND approver_user_id = ? "
                        + "AND archived_at IS NULL AND status = 'PENDING' AND expires_at > CURRENT_TIMESTAMP "
                        + "AND (draft_id IS NULL OR EXISTS (SELECT 1 FROM agent_meeting_booking_draft d "
                        + "WHERE d.draft_id = agent_approval.draft_id AND d.tenant_id = agent_approval.tenant_id "
                        + "AND d.owner_user_id = agent_approval.approver_user_id AND d.status = 'PENDING' "
                        + "AND d.archived_at IS NULL AND d.expires_at > CURRENT_TIMESTAMP "
                        + "AND d.message_id = agent_approval.message_id AND d.message_id IS NOT NULL) "
                        + "OR EXISTS (SELECT 1 FROM agent_personal_schedule_draft s "
                        + "WHERE s.draft_id = agent_approval.draft_id AND s.tenant_id = agent_approval.tenant_id "
                        + "AND s.owner_user_id = agent_approval.approver_user_id AND s.status = 'PENDING' "
                        + "AND s.archived_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP "
                        + "AND s.message_id = agent_approval.message_id AND s.message_id IS NOT NULL) "
                        + "OR (agent_approval.draft_type IS NOT NULL AND agent_approval.draft_data IS NOT NULL))",
                idempotencyKey, approvalId, tenantId, userId);
        if (updated == 0) return handleAlreadyProcessed(tenantId, userId, approvalId, idempotencyKey, "APPROVED");
        return get(tenantId, userId, approvalId);
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> reject(Long tenantId, Long userId, String approvalId,
                                      String idempotencyKey, String reason) {
        validateKey(idempotencyKey);
        int updated = jdbcTemplate.update("UPDATE agent_approval SET status = 'REJECTED', "
                        + "idempotency_key = ?, rejected_at = CURRENT_TIMESTAMP, rejected_reason = ?, "
                        + "updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? AND tenant_id = ? "
                        + "AND approver_user_id = ? AND archived_at IS NULL "
                        + "AND status = 'PENDING' AND expires_at > CURRENT_TIMESTAMP",
                idempotencyKey, reason, approvalId, tenantId, userId);
        if (updated == 0) return handleAlreadyProcessed(tenantId, userId, approvalId, idempotencyKey, "REJECTED");
        jdbcTemplate.update("UPDATE agent_meeting_booking_draft SET status = 'CANCELLED', "
                        + "updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'PENDING'",
                approvalId, tenantId, userId);
        jdbcTemplate.update("UPDATE agent_personal_schedule_draft SET status = 'CANCELLED', "
                        + "updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status = 'PENDING'",
                approvalId, tenantId, userId);
        jdbcTemplate.update("UPDATE agent_party_file_draft SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE approval_id = ? AND tenant_id = ? AND owner_user_id = ? AND status = 'PENDING'",
                approvalId, tenantId, userId);
        return get(tenantId, userId, approvalId);
    }

    /**
     * 记录恢复请求的幂等事实。实际 LangGraph resume 仍由 Agent Gateway 执行，
     * Java 负责校验审批已批准并防止同一审批被多次恢复。
     */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> recordResume(Long tenantId, Long userId, String approvalId,
                                            String resumeIdempotencyKey) {
        validateKey(resumeIdempotencyKey);
        Map<String, Object> approval = get(tenantId, userId, approvalId);
        if (!"APPROVED".equals(approval.get("status"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_RESUME_NOT_ALLOWED：审批当前状态不是 APPROVED");
        }
        int updated = jdbcTemplate.update("UPDATE agent_approval SET resume_idempotency_key = ?, "
                        + "resumed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? "
                        + "AND tenant_id = ? AND approver_user_id = ? AND status = 'APPROVED' "
                        + "AND archived_at IS NULL AND operation_id IS NOT NULL "
                        + "AND resume_idempotency_key IS NULL",
                resumeIdempotencyKey, approvalId, tenantId, userId);
        if (updated == 0) {
            Map<String, Object> existing = get(tenantId, userId, approvalId);
            if (resumeIdempotencyKey.equals(existing.get("resumeIdempotencyKey"))) return existing;
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_RESUME_CONFLICT：审批已经使用其他恢复幂等键");
        }
        return get(tenantId, userId, approvalId);
    }

    /** Claim a generic action while checking its durable Operation binding. */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> claimGenericExecution(Long tenantId, Long userId, String approvalId,
                                                      String idempotencyKey, String expectedDraftType,
                                                      String expectedOperationId) {
        validateKey(idempotencyKey);
        if (expectedDraftType == null || expectedDraftType.trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_EXECUTION_INVALID：草稿类型不能为空");
        }
        String validOperationId = requiredBinding(expectedOperationId, "operationId");
        // `idempotency_key` belongs to the user's ApprovalCard decision
        // (approve/reject), while the commit request has its own stable key
        // (for example `${approvalId}:commit`).  Comparing the two made every
        // correctly resumed generic/request/task action fail.  The durable
        // resume marker is the proof that the official HITL resume happened;
        // the conditional status transition is the single execution claim.
        int updated = jdbcTemplate.update("UPDATE agent_approval SET status = 'SUBMITTING', updated_at = CURRENT_TIMESTAMP "
                + "WHERE approval_id = ? AND tenant_id = ? AND approver_user_id = ? AND draft_type = ? "
                + "AND status = 'APPROVED' AND resume_idempotency_key IS NOT NULL "
                + "AND operation_id = ?",
                approvalId, tenantId, userId, expectedDraftType.trim(), validOperationId);
        Map<String, Object> current = get(tenantId, userId, approvalId);
        if (!validOperationId.equals(String.valueOf(current.get("operationId")))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_OPERATION_MISMATCH：审批与当前 Operation 不一致");
        }
        if (updated == 0 && !"COMPLETED".equals(current.get("status"))) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_EXECUTION_NOT_ALLOWED：单条审批尚未确认或正在执行");
        }
        current.put("replay", updated == 0 && "COMPLETED".equals(current.get("status")));
        return current;
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public void markGenericCompleted(Long tenantId, Long userId, String approvalId,
                                     String operationId, Map<String, Object> result) {
        String validOperationId = requiredBinding(operationId, "operationId");
        jdbcTemplate.update("UPDATE agent_approval SET status = 'COMPLETED', draft_data = draft_data || CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP "
                        + "WHERE approval_id = ? AND tenant_id = ? AND approver_user_id = ? "
                        + "AND operation_id = ? AND status = 'SUBMITTING'",
                JsonUtils.toJsonString(Collections.singletonMap("result", result == null ? new LinkedHashMap<>() : result)),
                approvalId, tenantId, userId, validOperationId);
    }

    /**
     * Complete a party-file commit after the MySQL business transaction has
     * returned a durable result. Party-file uses its own MySQL ledger as the
     * business idempotency boundary, so the PostgreSQL Approval can still be
     * APPROVED when this method is called during normal completion or crash
     * recovery. The operation and draft type checks keep this narrow adapter
     * from completing another Approval accidentally.
     */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> completePartyFileExecution(Long tenantId, Long userId,
                                                           String approvalId, String operationId,
                                                           Map<String, Object> result) {
        String validOperationId = requiredBinding(operationId, "operationId");
        Map<String, Object> current = get(tenantId, userId, approvalId);
        if (!"PARTY_FILE".equals(current.get("draftType"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "PARTY_FILE_APPROVAL_CONTEXT_INVALID：审批类型与党务文件提交不一致");
        }
        if (!validOperationId.equals(String.valueOf(current.get("operationId")))) {
            throw ServiceExceptionUtil.exception0(409,
                    "PARTY_FILE_APPROVAL_OPERATION_MISMATCH：审批与当前 Operation 不一致");
        }
        if ("COMPLETED".equals(current.get("status"))) return current;
        String status = String.valueOf(current.get("status"));
        if (!"APPROVED".equals(status) && !"SUBMITTING".equals(status)) {
            throw ServiceExceptionUtil.exception0(409,
                    "PARTY_FILE_APPROVAL_STATE_INVALID：审批当前状态不能完成党务文件提交");
        }
        int updated = jdbcTemplate.update("UPDATE agent_approval SET status = 'COMPLETED', "
                        + "draft_data = COALESCE(draft_data, '{}'::jsonb) || CAST(? AS jsonb), "
                        + "updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? AND tenant_id = ? "
                        + "AND approver_user_id = ? AND draft_type = 'PARTY_FILE' "
                        + "AND operation_id = ? AND status IN ('APPROVED', 'SUBMITTING')",
                JsonUtils.toJsonString(Collections.singletonMap("result",
                        result == null ? new LinkedHashMap<>() : result)), approvalId, tenantId, userId,
                validOperationId);
        if (updated == 0) {
            Map<String, Object> replay = get(tenantId, userId, approvalId);
            if ("COMPLETED".equals(replay.get("status"))) return replay;
            throw ServiceExceptionUtil.exception0(409,
                    "PARTY_FILE_APPROVAL_COMPLETE_CONFLICT：审批已被其他执行者推进");
        }
        return get(tenantId, userId, approvalId);
    }

    /**
     * Finish a task action after Java has re-read the external BPM state.
     *
     * <p>The normal execute path spans two stores: Flowable may commit before
     * the Approval row is marked COMPLETED.  This command closes that narrow
     * window without trusting a result supplied by Python: the controller
     * resolves the Flowable state first, then this method performs the
     * operation-bound, idempotent durable transition.</p>
     */
    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> completeGenericExecution(Long tenantId, Long userId, String approvalId,
                                                         String expectedDraftType, String expectedOperationId,
                                                         Map<String, Object> result) {
        String validDraftType = requiredBinding(expectedDraftType, "draftType");
        String validOperationId = requiredBinding(expectedOperationId, "operationId");
        Map<String, Object> current = get(tenantId, userId, approvalId);
        if (!validDraftType.equals(current.get("draftType"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_CONTEXT_INVALID：审批类型与恢复动作不一致");
        }
        if (!validOperationId.equals(String.valueOf(current.get("operationId")))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_OPERATION_MISMATCH：审批与当前 Operation 不一致");
        }
        String currentStatus = String.valueOf(current.get("status"));
        if ("COMPLETED".equals(currentStatus)) return current;
        if (!"SUBMITTING".equals(currentStatus)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_RECONCILE_NOT_ALLOWED：审批当前状态不能完成恢复");
        }
        int updated = jdbcTemplate.update("UPDATE agent_approval SET status = 'COMPLETED', "
                        + "draft_data = COALESCE(draft_data, '{}'::jsonb) || CAST(? AS jsonb), "
                        + "updated_at = CURRENT_TIMESTAMP WHERE approval_id = ? AND tenant_id = ? "
                        + "AND approver_user_id = ? AND draft_type = ? AND operation_id = ? "
                        + "AND status = 'SUBMITTING'",
                JsonUtils.toJsonString(Collections.singletonMap("result",
                        result == null ? new LinkedHashMap<>() : result)), approvalId, tenantId, userId,
                validDraftType, validOperationId);
        if (updated == 0) {
            Map<String, Object> replay = get(tenantId, userId, approvalId);
            if ("COMPLETED".equals(replay.get("status"))) return replay;
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_RECONCILE_CONFLICT：审批已经被其他执行者推进");
        }
        return get(tenantId, userId, approvalId);
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public void releaseGenericExecution(Long tenantId, Long userId, String approvalId, String operationId) {
        String validOperationId = requiredBinding(operationId, "operationId");
        jdbcTemplate.update("UPDATE agent_approval SET status = 'APPROVED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE approval_id = ? AND tenant_id = ? AND approver_user_id = ? "
                        + "AND operation_id = ? AND status = 'SUBMITTING'",
                approvalId, tenantId, userId, validOperationId);
    }

    private Map<String, Object> handleAlreadyProcessed(Long tenantId, Long userId, String approvalId,
                                                       String idempotencyKey, String expectedStatus) {
        Map<String, Object> existing = get(tenantId, userId, approvalId);
        if (expectedStatus.equals(existing.get("status"))
                && idempotencyKey.equals(existing.get("idempotencyKey"))) return existing;
        String actual = String.valueOf(existing.get("status"));
        if ("PENDING".equals(actual)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BINDING_INVALID：审批绑定的草稿已不存在、已过期或状态不一致");
        }
        throw ServiceExceptionUtil.exception0(409,
                "AGENT_APPROVAL_STATE_MISMATCH：审批当前状态为 " + actual + "，不能执行 " + expectedStatus);
    }

    private Map<String, Object> findApproval(Long tenantId, Long userId, String approvalId,
                                              boolean pendingOnly) {
        String statusPredicate = pendingOnly
                ? "AND a.archived_at IS NULL AND a.status = 'PENDING' AND a.expires_at > CURRENT_TIMESTAMP "
                : "";
        List<Map<String, Object>> rows = jdbcTemplate.query(
                approvalSelect() + " FROM agent_approval a "
                        + "LEFT JOIN agent_meeting_booking_draft d ON d.approval_id = a.approval_id "
                        + "LEFT JOIN agent_personal_schedule_draft s ON s.approval_id = a.approval_id "
                        + "LEFT JOIN agent_party_file_draft p ON p.approval_id = a.approval_id "
                + "WHERE a.approval_id = ? AND a.tenant_id = ? AND a.approver_user_id = ? "
                + "AND (d.draft_id IS NULL OR (a.message_id = d.message_id AND a.message_id IS NOT NULL)) "
                + "AND (s.draft_id IS NULL OR (a.message_id = s.message_id AND a.message_id IS NOT NULL)) "
                + "AND (p.draft_id IS NULL OR (a.message_id = p.message_id AND a.message_id IS NOT NULL)) "
                + statusPredicate,
                (rs, rowNum) -> mapApproval(rs), approvalId, tenantId, userId);
        if (rows.isEmpty()) {
            throw ServiceExceptionUtil.exception0(404,
                    pendingOnly ? "AGENT_APPROVAL_PENDING_NOT_FOUND：审批不存在、已处理或已过期"
                            : "AGENT_APPROVAL_NOT_FOUND：审批记录不存在或无权访问");
        }
        return pendingOnly ? card(rows.get(0)) : rows.get(0);
    }

    private String approvalSelect() {
        return "SELECT a.approval_id, a.tenant_id, a.approver_user_id, a.run_id, a.thread_id, a.message_id, a.task_id, a.operation_id, a.draft_id, "
                + "a.status, a.idempotency_key, a.resume_idempotency_key, a.expires_at, a.approved_at, "
                + "a.rejected_at, a.rejected_reason, a.resumed_at, "
                + "COALESCE(d.draft_data, s.draft_data, p.draft_data, a.draft_data)::text AS draft_data, "
                + "p.result_data::text AS party_result_data, "
                + "CASE WHEN p.draft_id IS NOT NULL THEN 'PARTY_FILE' "
                + "WHEN s.draft_id IS NOT NULL THEN 'PERSONAL_SCHEDULE' "
                + "WHEN d.draft_id IS NOT NULL THEN 'MEETING_BOOKING' ELSE a.draft_type END AS draft_type";
    }

    private Map<String, Object> mapApproval(java.sql.ResultSet rs) throws java.sql.SQLException {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("approvalId", rs.getString("approval_id"));
        // Python 的审批上下文契约使用 tenantId/userId，不能只返回 approver_user_id。
        result.put("tenantId", rs.getObject("tenant_id", Long.class));
        result.put("userId", rs.getObject("approver_user_id", Long.class));
        result.put("runId", rs.getString("run_id"));
        result.put("threadId", rs.getString("thread_id"));
        result.put("messageId", rs.getString("message_id"));
        result.put("taskId", rs.getString("task_id"));
        result.put("operationId", rs.getString("operation_id"));
        result.put("draftId", rs.getString("draft_id"));
        result.put("status", rs.getString("status"));
        result.put("idempotencyKey", rs.getString("idempotency_key"));
        result.put("resumeIdempotencyKey", rs.getString("resume_idempotency_key"));
        result.put("expiresAt", rs.getObject("expires_at"));
        result.put("approvedAt", rs.getObject("approved_at"));
        result.put("rejectedAt", rs.getObject("rejected_at"));
        result.put("rejectedReason", rs.getString("rejected_reason"));
        result.put("resumedAt", rs.getObject("resumed_at"));
        String draftData = rs.getString("draft_data");
        Map<String, Object> draft = draftData == null
                ? new LinkedHashMap<>() : JsonUtils.parseObject(draftData, Map.class);
        String partyResult = rs.getString("party_result_data");
        if (partyResult != null) draft.put("result", JsonUtils.parseObject(partyResult, Map.class));
        result.put("draft", draft);
        result.put("draftType", rs.getString("draft_type"));
        return result;
    }

    private Map<String, Object> card(Map<String, Object> approval) {
        Map<String, Object> result = new LinkedHashMap<>(approval);
        String draftType = String.valueOf(approval.get("draftType"));
        String cardType;
        if ("PERSONAL_SCHEDULE".equals(draftType)) {
            cardType = "personal_schedule_approval";
        } else if ("PARTY_FILE".equals(draftType)) {
            cardType = "party_file_approval";
        } else if ("APPROVAL_TASK".equals(draftType)) {
            cardType = "approval_task";
        } else if ("APPROVAL_REQUEST".equals(draftType)) {
            cardType = "approval_request";
        } else if ("APPROVAL_REQUEST_GENERIC".equals(draftType)) {
            // Generic BPM templates use the same ApprovalCard contract as
            // leave/trip requests.  They must never fall through to the
            // legacy meeting card, otherwise refresh/resume renders a
            // contract approval as a meeting operation.
            cardType = "approval_request";
        } else if ("APPROVAL_WITHDRAW".equals(draftType)) {
            cardType = "approval_withdraw";
        } else {
            cardType = "meeting_booking_approval";
        }
        result.put("cardType", cardType);
        result.put("card", approval.get("draft"));
        return result;
    }

    private void expireIfNeeded(Long tenantId, Long userId, String approvalId) {
        int expired = jdbcTemplate.update("UPDATE agent_approval SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE approval_id = ? AND tenant_id = ? AND approver_user_id = ? "
                        + "AND status = 'PENDING' AND expires_at <= CURRENT_TIMESTAMP",
                approvalId, tenantId, userId);
        if (expired > 0) cancelDraftForExpiredApproval(tenantId, userId, approvalId);
    }

    private void expireIfNeededByDraft(Long tenantId, Long userId, String draftId) {
        int expired = jdbcTemplate.update("UPDATE agent_approval SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE draft_id = ? AND tenant_id = ? AND approver_user_id = ? "
                        + "AND status = 'PENDING' AND expires_at <= CURRENT_TIMESTAMP",
                draftId, tenantId, userId);
        if (expired > 0) cancelDraftForExpiredApproval(tenantId, userId, draftId);
    }

    public void markExpired() {
        jdbcTemplate.update("UPDATE agent_approval SET status = 'EXPIRED', updated_at = CURRENT_TIMESTAMP "
                + "WHERE status = 'PENDING' AND expires_at <= CURRENT_TIMESTAMP");
        jdbcTemplate.update("UPDATE agent_meeting_booking_draft d SET status = 'CANCELLED', "
                + "updated_at = CURRENT_TIMESTAMP WHERE d.status = 'PENDING' AND EXISTS (SELECT 1 "
                + "FROM agent_approval a WHERE a.approval_id = d.approval_id AND a.tenant_id = d.tenant_id "
                + "AND a.approver_user_id = d.owner_user_id AND a.status = 'EXPIRED')");
        jdbcTemplate.update("UPDATE agent_personal_schedule_draft s SET status = 'CANCELLED', "
                + "updated_at = CURRENT_TIMESTAMP WHERE s.status = 'PENDING' AND EXISTS (SELECT 1 "
                + "FROM agent_approval a WHERE a.approval_id = s.approval_id AND a.tenant_id = s.tenant_id "
                + "AND a.approver_user_id = s.owner_user_id AND a.status = 'EXPIRED')");
        jdbcTemplate.update("UPDATE agent_party_file_draft p SET status = 'CANCELLED', "
                + "updated_at = CURRENT_TIMESTAMP WHERE p.status = 'PENDING' AND EXISTS (SELECT 1 "
                + "FROM agent_approval a WHERE a.approval_id = p.approval_id AND a.tenant_id = p.tenant_id "
                + "AND a.approver_user_id = p.owner_user_id AND a.status = 'EXPIRED')");
    }

    private void cancelDraftForExpiredApproval(Long tenantId, Long userId, String approvalOrDraftId) {
        jdbcTemplate.update("UPDATE agent_meeting_booking_draft d SET status = 'CANCELLED', "
                        + "updated_at = CURRENT_TIMESTAMP WHERE d.tenant_id = ? AND d.owner_user_id = ? "
                        + "AND d.status = 'PENDING' AND (d.approval_id = ? OR d.draft_id = ?) "
                        + "AND EXISTS (SELECT 1 FROM agent_approval a WHERE a.approval_id = d.approval_id "
                        + "AND a.tenant_id = d.tenant_id AND a.approver_user_id = d.owner_user_id "
                        + "AND a.status = 'EXPIRED')",
                tenantId, userId, approvalOrDraftId, approvalOrDraftId);
        jdbcTemplate.update("UPDATE agent_personal_schedule_draft s SET status = 'CANCELLED', "
                        + "updated_at = CURRENT_TIMESTAMP WHERE s.tenant_id = ? AND s.owner_user_id = ? "
                        + "AND s.status = 'PENDING' AND (s.approval_id = ? OR s.draft_id = ?) "
                        + "AND EXISTS (SELECT 1 FROM agent_approval a WHERE a.approval_id = s.approval_id "
                        + "AND a.tenant_id = s.tenant_id AND a.approver_user_id = s.owner_user_id "
                        + "AND a.status = 'EXPIRED')",
                tenantId, userId, approvalOrDraftId, approvalOrDraftId);
        jdbcTemplate.update("UPDATE agent_party_file_draft p SET status = 'CANCELLED', "
                + "updated_at = CURRENT_TIMESTAMP WHERE p.tenant_id = ? AND p.owner_user_id = ? "
                + "AND p.status = 'PENDING' AND (p.approval_id = ? OR p.draft_id = ?) "
                + "AND EXISTS (SELECT 1 FROM agent_approval a WHERE a.approval_id = p.approval_id "
                + "AND a.tenant_id = p.tenant_id AND a.approver_user_id = p.owner_user_id "
                + "AND a.status = 'EXPIRED')",
                tenantId, userId, approvalOrDraftId, approvalOrDraftId);
    }

    private void validateKey(String key) {
        if (key == null || key.trim().isEmpty() || key.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_IDEMPOTENCY_KEY_INVALID：缺少有效的审批幂等键");
        }
    }

    private void validateDraftBinding(Long tenantId, Long userId, String runId, String threadId,
                                      String messageId, String draftId, String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT run_id, thread_id, message_id, operation_id FROM agent_meeting_booking_draft "
                        + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND archived_at IS NULL",
                (rs, rowNum) -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("runId", rs.getString("run_id"));
                    result.put("threadId", rs.getString("thread_id"));
                    result.put("messageId", rs.getString("message_id"));
                    result.put("operationId", rs.getString("operation_id"));
                    return result;
                }, draftId, tenantId, userId);
        if (rows.isEmpty()) {
            throw ServiceExceptionUtil.exception0(404,
                    "AGENT_APPROVAL_BINDING_INVALID：预约草稿不存在或已归档");
        }
        Map<String, Object> draft = rows.get(0);
        if (!runId.equals(draft.get("runId")) || !threadId.equals(draft.get("threadId"))
                || !messageId.equals(draft.get("messageId"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BINDING_INVALID：审批与草稿的 run/thread/message 不一致");
        }
        if (!operationId.equals(draft.get("operationId"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BINDING_INVALID：审批与草稿的 operationId 不一致");
        }
    }

    private String requiredBinding(String value, String field) {
        if (value == null || value.trim().isEmpty() || value.length() > 128) {
            throw ServiceExceptionUtil.exception0(400,
                    "AGENT_APPROVAL_BINDING_INVALID：缺少有效的 " + field);
        }
        return value.trim();
    }
}
