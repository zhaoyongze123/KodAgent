package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Objects;


/** Agent 业务草稿持久化。草稿是业务状态，不属于 Agent checkpoint。 */
@Service
public class AgentDraftService {

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    @Resource
    private AgentApprovalService agentApprovalService;

    @Resource
    private MeetingBookingService meetingBookingService;

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> saveMeetingBookingDraft(Long tenantId, Long userId, Map<String, Object> request) {
        validateDraftRequest(request);
        captureSourceMeetingBookingSnapshot(userId, request);
        String idempotencyKey = String.valueOf(request.getOrDefault("idempotencyKey", "")).trim();
        if (idempotencyKey.isEmpty() || idempotencyKey.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "缺少有效的预约草稿幂等键");
        }
        String runId = requiredContext(request, "runId");
        String threadId = requiredContext(request, "threadId");
        String messageId = requiredContext(request, "messageId");
        String operationId = requiredContext(request, "operationId");
        Map<String, Object> existing = findPendingByIdempotency(
                tenantId, userId, idempotencyKey, runId, threadId, messageId, operationId);
        if (existing != null) return existing;

        String draftId = UUID.randomUUID().toString();
        String taskId = nullable(request.get("taskId"));
        Map<String, Object> draft = new LinkedHashMap<>(request);
        draft.put("ownerUserId", userId);
        draft.put("draftId", draftId);
        draft.put("createdAt", System.currentTimeMillis());
        String draftJson = JsonUtils.toJsonString(draft);
        try {
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, task_id, operation_id, "
                            + "idempotency_key, status, draft_data, expires_at) "
                            + "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', CAST(? AS jsonb), "
                            + "CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                    draftId, tenantId, userId, runId, threadId, messageId, taskId, operationId, idempotencyKey, draftJson);
        } catch (DuplicateKeyException ex) {
            Map<String, Object> concurrent = findPendingByIdempotency(
                    tenantId, userId, idempotencyKey, runId, threadId, messageId, operationId);
            if (concurrent != null) return concurrent;
            throw ServiceExceptionUtil.exception0(409, "预约草稿请求正在处理中");
        }
        String approvalId = agentApprovalService.create(tenantId, userId, runId, threadId,
                messageId, taskId, draftId, operationId);
        draft.put("approvalId", approvalId);
        jdbcTemplate.update("UPDATE agent_meeting_booking_draft SET approval_id = ?, draft_data = CAST(? AS jsonb) "
                        + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ?", approvalId,
                JsonUtils.toJsonString(draft), draftId, tenantId, userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("draftId", draftId);
        result.put("approvalId", approvalId);
        result.put("draft", draft);
        return result;
    }

    public Map<String, Object> getMeetingBookingDraft(Long tenantId, Long userId, String draftId) {
        Map<String, Object> draft = queryDraft(tenantId, userId, draftId);
        if (draft == null) {
            throw ServiceExceptionUtil.exception0(404, "预约草稿不存在或已过期");
        }
        return Collections.singletonMap("draft", draft);
    }

    public void deleteMeetingBookingDraft(Long tenantId, Long userId, String draftId) {
        getMeetingBookingDraft(tenantId, userId, draftId);
        updateStatus(tenantId, userId, draftId, "CANCELLED");
    }

    public void updateMeetingBookingDraftStatus(Long tenantId, Long userId, String draftId, String status) {
        if (!"SUBMITTED".equals(status) && !"CANCELLED".equals(status)) {
            throw ServiceExceptionUtil.exception0(400, "不支持的预约草稿状态");
        }
        getMeetingBookingDraft(tenantId, userId, draftId);
        updateStatus(tenantId, userId, draftId, status);
    }

    /** Claim only the draft belonging to the current durable Operation. */
    public Map<String, Object> claimMeetingBookingDraft(Long tenantId, Long userId, String draftId,
                                                        String approvalId, String operationId) {
        if (nullable(draftId) == null || nullable(approvalId) == null) {
            throw ServiceExceptionUtil.exception0(400,
                    "AGENT_APPROVAL_BINDING_INVALID：draftId 和 approvalId 不能为空");
        }
        String validOperationId = requiredContextValue(operationId, "operationId");
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "UPDATE agent_meeting_booking_draft d SET status = 'SUBMITTING', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE d.draft_id = ? AND d.tenant_id = ? AND d.owner_user_id = ? "
                        + "AND d.approval_id = ? "
                        + "AND d.operation_id = ? "
                        + "AND d.status = 'PENDING' AND d.archived_at IS NULL "
                        + "AND d.expires_at > CURRENT_TIMESTAMP "
                        + "AND d.approval_id IS NOT NULL AND EXISTS (SELECT 1 FROM agent_approval a "
                        + "WHERE a.approval_id = d.approval_id AND a.tenant_id = d.tenant_id "
                        + "AND a.approver_user_id = d.owner_user_id AND a.draft_id = d.draft_id "
                        + "AND a.run_id = d.run_id AND a.thread_id = d.thread_id "
                        + "AND a.message_id = d.message_id AND a.message_id IS NOT NULL "
                        + "AND a.operation_id = ? "
                        + "AND a.status = 'APPROVED') "
                        + "RETURNING d.draft_id, d.approval_id, d.run_id, d.thread_id, d.message_id, d.task_id, "
                        + "d.status, d.expires_at, d.draft_data::text",
                (rs, rowNum) -> enrichDraft(rs.getString("draft_data"), rs.getString("draft_id"),
                        rs.getString("approval_id"), rs.getString("run_id"), rs.getString("thread_id"),
                        rs.getString("message_id"), rs.getString("task_id"), rs.getString("status"),
                        rs.getObject("expires_at")), draftId, tenantId, userId, approvalId,
                validOperationId, validOperationId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(409,
                "AGENT_APPROVAL_REQUIRED：预约草稿必须先经过 APPROVED 审批");
        return rows.get(0);
    }

    public void validateMeetingBookingBinding(Map<String, Object> storedDraft, String subject,
                                              Long meetingRoomId, LocalDateTime startTime,
                                              LocalDateTime endTime, List<Long> attendeeUserIds) {
        if (!String.valueOf(storedDraft.get("subject")).equals(subject)
                || !String.valueOf(storedDraft.get("meetingRoomId")).equals(String.valueOf(meetingRoomId))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_DRAFT_BINDING_MISMATCH：提交内容与审批草稿不一致");
        }
        LocalDateTime storedStart = parseDate(storedDraft.get("startTime"));
        LocalDateTime storedEnd = parseDate(storedDraft.get("endTime"));
        if (!startTime.equals(storedStart) || !endTime.equals(storedEnd)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_DRAFT_BINDING_MISMATCH：提交时间与审批草稿不一致");
        }
        Object storedAttendees = storedDraft.get("attendeeUserIds");
        if (storedAttendees != null && attendeeUserIds != null
                && !String.valueOf(storedAttendees).equals(String.valueOf(attendeeUserIds))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_DRAFT_BINDING_MISMATCH：提交参会人与审批草稿不一致");
        }
    }

    /**
     * Meeting operations are business facts persisted before the approval
     * boundary.  The agent may not select an operation during commit.
     */
    public String meetingBookingOperation(Map<String, Object> storedDraft) {
        String operation = String.valueOf(storedDraft.getOrDefault("operation", "CREATE"))
                .trim().toUpperCase(java.util.Locale.ROOT);
        if (!java.util.Set.of("CREATE", "UPDATE", "CANCEL").contains(operation)) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_DRAFT_BINDING_MISMATCH：会议草稿操作无效");
        }
        return operation;
    }

    public Long sourceMeetingBookingId(Map<String, Object> storedDraft) {
        Object value = storedDraft.get("sourceBookingId");
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_DRAFT_BINDING_MISMATCH：会议变更草稿缺少来源预约");
        }
        try {
            return Long.valueOf(String.valueOf(value));
        } catch (NumberFormatException ex) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_DRAFT_BINDING_MISMATCH：来源预约编号无效");
        }
    }

    /** Store the final facade response so an exact network retry is harmless. */
    public void markMeetingBookingDraftSubmitted(Long tenantId, Long userId, String draftId,
                                                 String operationId, Map<String, Object> result) {
        String validOperationId = requiredContextValue(operationId, "operationId");
        int updated = jdbcTemplate.update(
                "UPDATE agent_meeting_booking_draft SET status = 'SUBMITTED', result_data = CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP "
                        + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND operation_id = ? AND status = 'SUBMITTING' AND archived_at IS NULL",
                JsonUtils.toJsonString(result == null ? Collections.emptyMap() : result), draftId, tenantId, userId,
                validOperationId);
        if (updated == 0) {
            throw ServiceExceptionUtil.exception0(409, "预约草稿状态已改变，禁止重复提交");
        }
    }

    /** Return a prior completed response for the exact authenticated draft and Operation. */
    public Map<String, Object> findSubmittedMeetingBookingResult(Long tenantId, Long userId,
                                                                   String draftId, String approvalId,
                                                                   String operationId) {
        String validOperationId = requiredContextValue(operationId, "operationId");
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT COALESCE(result_data, jsonb_build_object('success', true, 'message', '会议预约已处理'))::text "
                        + "FROM agent_meeting_booking_draft WHERE draft_id = ? AND approval_id = ? "
                        + "AND tenant_id = ? AND owner_user_id = ? "
                        + "AND operation_id = ? "
                        + "AND status = 'SUBMITTED' AND archived_at IS NULL",
                (rs, rowNum) -> JsonUtils.parseObject(rs.getString(1), Map.class),
                draftId, approvalId, tenantId, userId, validOperationId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /**
     * Read the durable commit marker used to reconcile a lost response.
     *
     * <p>This endpoint deliberately exposes only the authenticated user's
     * draft, approval and final response.  It does not resurrect a pending
     * draft and it does not perform a business write.</p>
     */
    public Map<String, Object> findMeetingBookingCommitStatus(Long tenantId, Long userId,
                                                                String draftId, String approvalId,
                                                                String operationId) {
        String validOperationId = requiredContextValue(operationId, "operationId");
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, result_data::text FROM agent_meeting_booking_draft "
                        + "WHERE draft_id = ? AND approval_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND operation_id = ? "
                        + "AND archived_at IS NULL",
                (rs, rowNum) -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("status", rs.getString("status"));
                    String resultJson = rs.getString("result_data");
                    result.put("result", resultJson == null
                            ? new LinkedHashMap<>() : JsonUtils.parseObject(resultJson, Map.class));
                    return result;
                }, draftId, approvalId, tenantId, userId, validOperationId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** Only the persisted draft may authorize an attendee-conflict override. */
    public boolean hasStoredConflictOverride(Map<String, Object> storedDraft) {
        if (storedDraft == null) return false;
        Object value = storedDraft.get("hasConflictOverride");
        return Boolean.TRUE.equals(value) || "true".equalsIgnoreCase(String.valueOf(value));
    }

    public void restoreMeetingBookingDraftPending(Long tenantId, Long userId, String draftId, String operationId) {
        String validOperationId = requiredContextValue(operationId, "operationId");
        jdbcTemplate.update(
                "UPDATE agent_meeting_booking_draft SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP "
                + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? "
                + "AND operation_id = ? AND status = 'SUBMITTING' AND archived_at IS NULL",
                draftId, tenantId, userId, validOperationId);
    }

    private Map<String, Object> queryDraft(Long tenantId, Long userId, String draftId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT draft_id, approval_id, run_id, thread_id, message_id, task_id, status, "
                        + "expires_at, draft_data::text FROM agent_meeting_booking_draft "
                        + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND status = 'PENDING' AND archived_at IS NULL "
                        + "AND expires_at > CURRENT_TIMESTAMP",
                (rs, rowNum) -> enrichDraft(rs.getString("draft_data"), rs.getString("draft_id"),
                        rs.getString("approval_id"), rs.getString("run_id"), rs.getString("thread_id"),
                        rs.getString("message_id"), rs.getString("task_id"), rs.getString("status"),
                        rs.getObject("expires_at")),
                draftId, tenantId, userId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> findPendingByIdempotency(Long tenantId, Long userId, String idempotencyKey,
                                                         String runId, String threadId, String messageId,
                                                         String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT draft_id, approval_id, run_id, thread_id, message_id, task_id, status, "
                        + "expires_at, draft_data::text FROM agent_meeting_booking_draft "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ? "
                        + "AND run_id = ? AND thread_id = ? AND message_id = ? "
                        + "AND operation_id = ? "
                        + "AND status = 'PENDING' AND archived_at IS NULL "
                        + "AND expires_at > CURRENT_TIMESTAMP",
                (rs, rowNum) -> enrichDraft(rs.getString("draft_data"), rs.getString("draft_id"),
                        rs.getString("approval_id"), rs.getString("run_id"), rs.getString("thread_id"),
                        rs.getString("message_id"), rs.getString("task_id"), rs.getString("status"),
                        rs.getObject("expires_at")),
                tenantId, userId, idempotencyKey, runId, threadId, messageId, operationId);
        if (rows.isEmpty()) return null;
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("draftId", rows.get(0).get("draftId"));
        result.put("approvalId", rows.get(0).get("approvalId"));
        result.put("draft", rows.get(0));
        return result;
    }

    private void validateDraftRequest(Map<String, Object> request) {
        if (request == null) {
            throw ServiceExceptionUtil.exception0(400, "预约草稿请求不能为空");
        }
        String operation = String.valueOf(request.getOrDefault("operation", "CREATE"))
                .trim().toUpperCase(java.util.Locale.ROOT);
        if (!java.util.Set.of("CREATE", "UPDATE", "CANCEL").contains(operation)) {
            throw ServiceExceptionUtil.exception0(400, "会议草稿操作必须是 CREATE、UPDATE 或 CANCEL");
        }
        if (!"CANCEL".equals(operation)) {
            String subject = String.valueOf(request.getOrDefault("subject", "")).trim();
            String start = String.valueOf(request.getOrDefault("startTime", "")).trim();
            String end = String.valueOf(request.getOrDefault("endTime", "")).trim();
            Object roomId = request.get("meetingRoomId");
            if (subject.isEmpty() || subject.length() > 200) {
                throw ServiceExceptionUtil.exception0(400, "会议主题不能为空且长度不能超过 200 个字符");
            }
            if (!(roomId instanceof Number) || start.isEmpty() || end.isEmpty()) {
                throw ServiceExceptionUtil.exception0(400, "会议室、开始时间和结束时间参数无效");
            }
        }
        if (("UPDATE".equals(operation) || "CANCEL".equals(operation))
                && nullable(request.get("sourceBookingId")) == null) {
            throw ServiceExceptionUtil.exception0(400, "会议变更草稿缺少来源预约编号");
        }
        if (nullable(request.get("runId")) == null || nullable(request.get("threadId")) == null
                || nullable(request.get("messageId")) == null || nullable(request.get("operationId")) == null) {
            throw ServiceExceptionUtil.exception0(400, "预约草稿缺少 Agent Run 上下文");
        }
        Object attendees = request.get("attendeeUserIds");
        if (attendees != null && !(attendees instanceof List)) {
            throw ServiceExceptionUtil.exception0(400, "参会人 ID 必须是数组");
        }
    }

    /**
     * UPDATE/CANCEL drafts must be bound to an actual applicant-owned booking
     * before the approval card is shown.  The client can name the source ID,
     * but it must never be trusted to provide its version snapshot: otherwise
     * an old card could overwrite a booking which was changed in another OA
     * client while the user was deciding.
     */
    private void captureSourceMeetingBookingSnapshot(Long userId, Map<String, Object> request) {
        String operation = requestedMeetingBookingOperation(request);
        if ("CREATE".equals(operation)) {
            return;
        }
        Long sourceId = requestedSourceMeetingBookingId(request);
        MeetingBookingDO source = meetingBookingService.getMeetingBooking(sourceId);
        if (source == null) {
            throw ServiceExceptionUtil.exception0(404, "来源会议预约不存在或已删除");
        }
        if (!Objects.equals(userId, source.getApplicantUserId())) {
            throw ServiceExceptionUtil.exception0(403, "只能修改或取消由当前用户发起的会议预约");
        }
        if (!Objects.equals(source.getStatus(), 1)) {
            throw ServiceExceptionUtil.exception0(409, "来源会议预约已取消，不能再次修改或取消");
        }
        if (source.getStartTime() == null || !LocalDateTime.now().isBefore(source.getStartTime())) {
            throw ServiceExceptionUtil.exception0(409, "会议已开始，不能修改或取消");
        }
        // Always overwrite values supplied by the agent with Java's current
        // business fact. The facade repeats the comparison immediately before
        // the irreversible write.
        request.put("sourceBookingId", sourceId);
        request.put("sourceStartTime", formatDate(source.getStartTime()));
        request.put("sourceEndTime", formatDate(source.getEndTime()));
        request.put("sourceVersion", source.getUpdateTime() == null ? "" : source.getUpdateTime().toString());
    }

    private String requestedMeetingBookingOperation(Map<String, Object> request) {
        return String.valueOf(request.getOrDefault("operation", "CREATE")).trim()
                .toUpperCase(java.util.Locale.ROOT);
    }

    private Long requestedSourceMeetingBookingId(Map<String, Object> request) {
        String value = nullable(request.get("sourceBookingId"));
        try {
            return value == null ? null : Long.valueOf(value);
        } catch (NumberFormatException ex) {
            throw ServiceExceptionUtil.exception0(400, "会议变更草稿来源预约编号无效");
        }
    }

    private String formatDate(LocalDateTime value) {
        return value == null ? "" : value.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
    }

    private void updateStatus(Long tenantId, Long userId, String draftId, String status) {
        int updated = jdbcTemplate.update(
                "UPDATE agent_meeting_booking_draft SET status = ?, updated_at = CURRENT_TIMESTAMP "
                        + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND status = 'PENDING' AND archived_at IS NULL",
                status, draftId, tenantId, userId);
        if (updated == 0) {
            throw ServiceExceptionUtil.exception0(404, "预约草稿不存在、已处理或已过期");
        }
    }

    private String nullable(Object value) {
        if (value == null) return null;
        String text = String.valueOf(value).trim();
        return text.isEmpty() ? null : text;
    }

    private String requiredContext(Map<String, Object> request, String field) {
        return requiredContextValue(request.get(field), field);
    }

    private String requiredContextValue(Object rawValue, String field) {
        String value = nullable(rawValue);
        if (value == null || value.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "预约草稿缺少有效的 Agent 上下文：" + field);
        }
        return value;
    }

    private LocalDateTime parseDate(Object value) {
        if (value == null) return null;
        String text = String.valueOf(value);
        for (DateTimeFormatter formatter : new DateTimeFormatter[]{
                DateTimeFormatter.ISO_LOCAL_DATE_TIME,
                DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
                DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")}) {
            try { return LocalDateTime.parse(text, formatter); }
            catch (DateTimeParseException ignored) { }
        }
        throw ServiceExceptionUtil.exception0(409, "AGENT_DRAFT_BINDING_MISMATCH：草稿时间格式无效");
    }

    private Map<String, Object> enrichDraft(String json, String draftId, String approvalId,
                                             String runId, String threadId, String messageId,
                                             String taskId, String status, Object expiresAt) {
        Map<String, Object> draft = JsonUtils.parseObject(json, Map.class);
        if (draft == null) draft = new LinkedHashMap<>();
        draft.put("draftId", draftId);
        draft.put("approvalId", approvalId);
        draft.put("runId", runId);
        draft.put("threadId", threadId);
        draft.put("messageId", messageId);
        draft.put("taskId", taskId);
        draft.put("status", status);
        draft.put("expiresAt", expiresAt);
        return draft;
    }
}
