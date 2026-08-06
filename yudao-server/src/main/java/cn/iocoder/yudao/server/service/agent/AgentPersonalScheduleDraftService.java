package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * Durable confirmation boundary for PERSONAL_SCHEDULE only.
 *
 * <p>The Python agent may create a draft, but cannot write a calendar event.
 * This service re-reads approval, owner, source version and conflicts in the
 * same final transaction before delegating to the system schedule service.</p>
 */
@Service
public class AgentPersonalScheduleDraftService {

    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Resource @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Resource private PersonalScheduleService personalScheduleService;
    @Resource private AgentPersonalScheduleBusinessCommitService businessCommitService;

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> save(Long tenantId, Long userId, Map<String, Object> request) {
        validateDraftRequest(request);
        String operation = required(request, "operation").toUpperCase(Locale.ROOT);
        String idempotencyKey = required(request, "idempotencyKey");
        String runId = required(request, "runId");
        String threadId = required(request, "threadId");
        String messageId = required(request, "messageId");
        String operationId = required(request, "operationId");
        if (idempotencyKey.length() > 128 || runId.length() > 128 || threadId.length() > 128 || messageId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "日程草稿上下文或幂等键过长");
        }
        if (operationId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "日程草稿 operationId 无效");
        }
        Map<String, Object> existing = findPending(tenantId, userId, idempotencyKey, runId, threadId, messageId, operationId);
        if (existing != null) return existing;

        Long sourceId = number(request.get("sourceScheduleId"));
        String sourceVersion = null;
        if (!"CREATE".equals(operation)) {
            if (sourceId == null) throw ServiceExceptionUtil.exception0(400, "修改或取消日程必须指定 sourceScheduleId");
            PersonalScheduleDO source = personalScheduleService.getPersonalSchedule(userId, sourceId);
            sourceVersion = version(source);
        }
        validatePayload(operation, request);

        String draftId = UUID.randomUUID().toString();
        String approvalId = UUID.randomUUID().toString();
        Map<String, Object> draft = new LinkedHashMap<>(request);
        draft.put("draftId", draftId);
        draft.put("approvalId", approvalId);
        draft.put("sourceType", "PERSONAL_SCHEDULE");
        draft.put("ownerUserId", userId);
        draft.put("operationId", operationId);
        draft.put("sourceVersion", sourceVersion);
        draft.put("createdAt", System.currentTimeMillis());
        jdbcTemplate.update("INSERT INTO agent_personal_schedule_draft "
                        + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, task_id, "
                        + "operation_id, idempotency_key, operation, source_schedule_id, source_version, status, draft_data, expires_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', CAST(? AS jsonb), CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                draftId, approvalId, tenantId, userId, runId, threadId, messageId, nullable(request.get("taskId")),
                operationId, idempotencyKey, operation, sourceId, sourceVersion, JsonUtils.toJsonString(draft));
        // AgentApprovalService binds both meeting and personal-schedule
        // drafts. Final commit still independently re-checks this binding in
        // the same transaction as the business write.
        jdbcTemplate.update("INSERT INTO agent_approval "
                        + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, task_id, operation_id, draft_id, status, expires_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                approvalId, tenantId, userId, runId, threadId, messageId, nullable(request.get("taskId")), operationId, draftId);
        return result(draftId, approvalId, draft);
    }

    public Map<String, Object> commit(Long tenantId, Long userId, String draftId, String approvalId,
                                      String operationId) {
        Map<String, Object> submitted = findSubmitted(tenantId, userId, draftId, approvalId, operationId);
        if (submitted != null) return submitted;
        // The business ledger is authoritative for the narrow cross-database
        // crash window. Recovering it before claiming the PostgreSQL draft
        // avoids a second calendar mutation after the MySQL transaction has
        // already committed.
        Map<String, Object> businessResult = businessCommitService.findCommittedByDraft(tenantId, userId, draftId);
        if (businessResult != null) {
            int repaired = jdbcTemplate.update("UPDATE agent_personal_schedule_draft SET status = 'SUBMITTED', "
                            + "result_data = CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP "
                            + "WHERE draft_id = ? AND approval_id = ? AND tenant_id = ? AND owner_user_id = ? "
                            + "AND status IN ('PENDING', 'SUBMITTING')",
                    JsonUtils.toJsonString(businessResult), draftId, approvalId, tenantId, userId);
            if (repaired == 1 || findSubmitted(tenantId, userId, draftId, approvalId, operationId) != null) {
                return businessResult;
            }
            throw ServiceExceptionUtil.exception0(409, "日程业务已提交，但 Agent 结果标记尚未恢复，请稍后重试");
        }
        Map<String, Object> draft = claimApproved(tenantId, userId, draftId, approvalId, operationId);
        boolean businessCommitted = false;
        try {
            Map<String, Object> response = businessCommitService.commit(tenantId, userId, draftId, draft);
            businessCommitted = true;
            int updated = jdbcTemplate.update("UPDATE agent_personal_schedule_draft SET status = 'SUBMITTED', result_data = CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP "
                            + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? AND status = 'SUBMITTING'",
                    JsonUtils.toJsonString(response), draftId, tenantId, userId);
            if (updated != 1) throw ServiceExceptionUtil.exception0(409, "日程草稿状态已改变，禁止重复提交");
            return response;
        } catch (RuntimeException ex) {
            // The schedule service uses the business datasource while this
            // marker uses the Agent event datasource. Once the business write
            // returned, restoring PENDING could permit a second real write.
            if (!businessCommitted) {
                jdbcTemplate.update("UPDATE agent_personal_schedule_draft SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP "
                                + "WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? AND status = 'SUBMITTING'",
                        draftId, tenantId, userId);
            }
            throw ex;
        }
    }

    public Map<String, Object> detail(Long userId, Long scheduleId) {
        PersonalScheduleDO source = personalScheduleService.getPersonalSchedule(userId, scheduleId);
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("sourceType", "PERSONAL_SCHEDULE"); event.put("sourceId", source.getId()); event.put("editable", true);
        event.put("title", source.getTitle()); event.put("startTime", source.getStartTime()); event.put("endTime", source.getEndTime());
        event.put("location", source.getLocation()); event.put("description", source.getDescription()); event.put("otherParticipants", source.getOtherParticipants());
        event.put("attendeeUserIds", personalScheduleService.getAttendeeUserIds(source.getId())); event.put("version", version(source));
        return event;
    }

    public Map<String, Object> getDraft(Long tenantId, Long userId, String draftId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT approval_id, draft_data::text FROM agent_personal_schedule_draft WHERE draft_id = ? "
                        + "AND tenant_id = ? AND owner_user_id = ? AND status = 'PENDING' "
                        + "AND archived_at IS NULL AND expires_at > CURRENT_TIMESTAMP",
                (rs, rowNum) -> result(draftId, rs.getString("approval_id"), JsonUtils.parseObject(rs.getString("draft_data"), Map.class)),
                draftId, tenantId, userId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(404, "个人日程草稿不存在、已处理或已过期");
        return rows.get(0);
    }

    private Map<String, Object> claimApproved(Long tenantId, Long userId, String draftId, String approvalId,
                                              String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "UPDATE agent_personal_schedule_draft d SET status = 'SUBMITTING', updated_at = CURRENT_TIMESTAMP "
                        + "WHERE d.draft_id = ? AND d.approval_id = ? AND d.tenant_id = ? AND d.owner_user_id = ? "
                        + "AND d.status = 'PENDING' AND d.archived_at IS NULL AND d.expires_at > CURRENT_TIMESTAMP "
                        + "AND d.operation_id = ? "
                        + "AND EXISTS (SELECT 1 FROM agent_approval a WHERE a.approval_id = d.approval_id "
                        + "AND a.tenant_id = d.tenant_id AND a.approver_user_id = d.owner_user_id "
                        + "AND a.draft_id = d.draft_id AND a.run_id = d.run_id AND a.thread_id = d.thread_id "
                        + "AND a.message_id = d.message_id AND a.status = 'APPROVED' "
                        + "AND a.operation_id = ?) RETURNING d.draft_data::text",
                (rs, rowNum) -> JsonUtils.parseObject(rs.getString(1), Map.class), draftId, approvalId, tenantId, userId,
                operationId, operationId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_REQUIRED：个人日程草稿必须先经过 APPROVED 确认");
        return rows.get(0);
    }

    private Map<String, Object> findSubmitted(Long tenantId, Long userId, String draftId, String approvalId,
                                               String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT COALESCE(result_data, jsonb_build_object('success', true, 'operation', operation, "
                        + "'scheduleId', source_schedule_id, 'message', '个人日程已处理'))::text "
                        + "FROM agent_personal_schedule_draft WHERE draft_id = ? AND approval_id = ? "
                        + "AND tenant_id = ? AND owner_user_id = ? AND status = 'SUBMITTED' AND archived_at IS NULL "
                        + "AND operation_id = ?",
                (rs, rowNum) -> JsonUtils.parseObject(rs.getString(1), Map.class), draftId, approvalId, tenantId, userId,
                operationId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    /** Read the durable draft marker without attempting another business write. */
    public Map<String, Object> findCommitStatus(Long tenantId, Long userId, String draftId,
                                                String approvalId, String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, idempotency_key, result_data::text FROM agent_personal_schedule_draft "
                        + "WHERE draft_id = ? AND approval_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND operation_id = ? AND archived_at IS NULL",
                (rs, rowNum) -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("status", rs.getString("status"));
                    result.put("idempotencyKey", rs.getString("idempotency_key"));
                    String data = rs.getString("result_data");
                    result.put("result", data == null ? new LinkedHashMap<>() : JsonUtils.parseObject(data, Map.class));
                    return result;
                }, draftId, approvalId, tenantId, userId, operationId);
        if (rows.isEmpty()) return null;
        Map<String, Object> result = rows.get(0);
        String status = String.valueOf(result.get("status"));
        if (!"SUBMITTED".equals(status)) {
            Map<String, Object> committed = businessCommitService.findCommittedByIdempotency(
                    tenantId, userId, nullable(result.get("idempotencyKey")));
            if (committed != null) {
                result.put("status", "SUBMITTED");
                result.put("result", committed);
            }
        }
        result.remove("idempotencyKey");
        return result;
    }

    private void validateDraftRequest(Map<String, Object> request) {
        if (request == null) throw ServiceExceptionUtil.exception0(400, "日程草稿不能为空");
        String operation = required(request, "operation").toUpperCase(Locale.ROOT);
        if (!Set.of("CREATE", "UPDATE", "CANCEL").contains(operation)) throw ServiceExceptionUtil.exception0(400, "日程操作必须是 CREATE、UPDATE 或 CANCEL");
        required(request, "idempotencyKey"); required(request, "runId"); required(request, "threadId");
        required(request, "messageId"); required(request, "operationId");
    }
    private void validatePayload(String operation, Map<String, Object> request) {
        if ("CANCEL".equals(operation)) return;
        String title = required(request, "title");
        if (title.length() > 200) throw ServiceExceptionUtil.exception0(400, "日程标题不能超过 200 个字符");
        LocalDateTime start = parseTime(request.get("startTime")); LocalDateTime end = parseTime(request.get("endTime"));
        if (!start.isBefore(end)) throw ServiceExceptionUtil.exception0(400, "日程结束时间必须晚于开始时间");
    }
    private Map<String, Object> findPending(Long tenantId, Long userId, String key, String run, String thread,
                                            String message, String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query("SELECT draft_id, approval_id, draft_data::text FROM agent_personal_schedule_draft "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ? AND run_id = ? AND thread_id = ? AND message_id = ? "
                        + "AND status = 'PENDING' AND archived_at IS NULL AND expires_at > CURRENT_TIMESTAMP "
                        + "AND operation_id = ?",
                (rs, rowNum) -> result(rs.getString("draft_id"), rs.getString("approval_id"), JsonUtils.parseObject(rs.getString("draft_data"), Map.class)),
                tenantId, userId, key, run, thread, message, operationId);
        return rows.isEmpty() ? null : rows.get(0);
    }
    private Map<String, Object> result(String draftId, String approvalId, Map<String, Object> draft) { Map<String, Object> r = new LinkedHashMap<>(); r.put("draftId", draftId); r.put("approvalId", approvalId); r.put("draft", draft); return r; }
    private String version(PersonalScheduleDO source) { return source.getUpdateTime() == null ? "" : TIME.format(source.getUpdateTime()); }
    private LocalDateTime parseTime(Object value) { try { return LocalDateTime.parse(String.valueOf(value).replace('T', ' '), TIME); } catch (Exception e) { throw ServiceExceptionUtil.exception0(400, "日程时间格式必须为 yyyy-MM-dd HH:mm:ss"); } }
    private String required(Map<String, Object> value, String key) { String result = nullable(value.get(key)); if (result == null) throw ServiceExceptionUtil.exception0(400, "缺少 " + key); return result; }
    private String nullable(Object value) { String result = value == null ? null : String.valueOf(value).trim(); return result == null || result.isEmpty() || "null".equalsIgnoreCase(result) ? null : result; }
    private Long number(Object value) { try { String text = nullable(value); return text == null ? null : Long.valueOf(text); } catch (NumberFormatException e) { throw ServiceExceptionUtil.exception0(400, "sourceScheduleId 必须是数字"); } }
}
