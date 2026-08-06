package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import javax.sql.DataSource;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Business-database commit boundary for one personal-schedule Effect.
 *
 * <p>The Agent draft and Approval live in PostgreSQL, while the calendar lives
 * in MySQL.  This service keeps a small idempotency ledger in the business
 * database and commits the ledger together with the calendar mutation.  A
 * process crash after the MySQL commit therefore leaves a durable business
 * result that can be reconciled without executing the mutation twice.</p>
 */
@Service
public class AgentPersonalScheduleBusinessCommitService {

    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    @Resource
    private DataSource dataSource;
    @Resource
    private PersonalScheduleService personalScheduleService;
    @Resource
    private MeetingBookingService meetingBookingService;

    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initialize() {
        jdbcTemplate = new JdbcTemplate(dataSource);
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> commit(Long tenantId, Long userId, String draftId,
                                      Map<String, Object> draft) {
        String operation = required(draft, "operation").toUpperCase(Locale.ROOT);
        String idempotencyKey = required(draft, "idempotencyKey");
        Map<String, Object> existing = findByIdempotencyForUpdate(tenantId, userId, idempotencyKey);
        if (existing != null && "SUCCEEDED".equals(existing.get("status"))) {
            return resultData(existing);
        }
        if (existing == null) {
            jdbcTemplate.update("INSERT INTO agent_personal_schedule_effect "
                            + "(tenant_id, owner_user_id, operation_id, draft_id, idempotency_key, operation, status) "
                            + "VALUES (?, ?, ?, ?, ?, ?, 'PROCESSING')",
                    tenantId, userId, nullable(draft.get("operationId")), draftId, idempotencyKey, operation);
        } else {
            jdbcTemplate.update("UPDATE agent_personal_schedule_effect SET status = 'PROCESSING', "
                            + "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    existing.get("id"));
        }

        Long scheduleId;
        if ("CREATE".equals(operation)) {
            validateFinalConflict(userId, draft, null);
            scheduleId = personalScheduleService.createPersonalSchedule(userId, saveRequest(draft, null));
        } else {
            Long sourceId = number(draft.get("sourceScheduleId"));
            lockSchedule(tenantId, userId, sourceId);
            PersonalScheduleDO source = personalScheduleService.getPersonalSchedule(userId, sourceId);
            if (!Objects.equals(version(source), nullable(draft.get("sourceVersion")))) {
                throw ServiceExceptionUtil.exception0(409,
                        "PERSONAL_SCHEDULE_VERSION_CONFLICT：日程已被修改，请重新确认");
            }
            scheduleId = sourceId;
            if ("UPDATE".equals(operation)) {
                validateFinalConflict(userId, draft, sourceId);
                personalScheduleService.updatePersonalSchedule(userId, saveRequest(draft, sourceId));
            } else if ("CANCEL".equals(operation)) {
                personalScheduleService.deletePersonalSchedule(userId, sourceId);
            } else {
                throw ServiceExceptionUtil.exception0(400, "不支持的个人日程操作");
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("success", true);
        result.put("operation", operation);
        result.put("scheduleId", scheduleId);
        result.put("message", "CREATE".equals(operation) ? "个人日程已创建"
                : "UPDATE".equals(operation) ? "个人日程已更新" : "个人日程已取消");
        jdbcTemplate.update("UPDATE agent_personal_schedule_effect SET status = 'SUCCEEDED', "
                        + "result_data = ?, updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? "
                        + "AND owner_user_id = ? AND idempotency_key = ?",
                JsonUtils.toJsonString(result), tenantId, userId, idempotencyKey);
        return result;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findCommittedByDraft(Long tenantId, Long userId, String draftId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, result_data FROM agent_personal_schedule_effect "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND draft_id = ?",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, draftId);
        if (rows.isEmpty() || !"SUCCEEDED".equals(rows.get(0).get("status"))) return null;
        String json = nullable(rows.get(0).get("result"));
        return parseResultData(json);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findCommittedByIdempotency(Long tenantId, Long userId, String idempotencyKey) {
        Map<String, Object> row = findByIdempotency(tenantId, userId, idempotencyKey);
        if (row == null || !"SUCCEEDED".equals(row.get("status"))) return null;
        return resultData(row);
    }

    private Map<String, Object> findByIdempotencyForUpdate(Long tenantId, Long userId, String key) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT id, status, CAST(result_data AS CHAR) AS result_data FROM agent_personal_schedule_effect "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ? FOR UPDATE",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", rs.getLong("id"));
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, key);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> findByIdempotency(Long tenantId, Long userId, String key) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, result_data FROM agent_personal_schedule_effect "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ?",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, key);
        return rows.isEmpty() ? null : rows.get(0);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resultData(Map<String, Object> row) {
        String json = nullable(row.get("result"));
        return parseResultData(json);
    }

    /** Keep the public result shape stable across a fresh commit and Ledger replay. */
    @SuppressWarnings("unchecked")
    private Map<String, Object> parseResultData(String json) {
        if (json == null) return Collections.emptyMap();
        Map<String, Object> result = JsonUtils.parseObject(json, Map.class);
        if (result == null) return Collections.emptyMap();
        Object scheduleId = result.get("scheduleId");
        if (scheduleId instanceof Number && !(scheduleId instanceof Long)) {
            result.put("scheduleId", ((Number) scheduleId).longValue());
        }
        return result;
    }

    private void lockSchedule(Long tenantId, Long userId, Long scheduleId) {
        if (scheduleId == null) {
            throw ServiceExceptionUtil.exception0(400, "修改或取消日程必须指定 sourceScheduleId");
        }
        List<Long> rows = jdbcTemplate.query(
                "SELECT id FROM system_personal_schedule WHERE id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND deleted = 0 FOR UPDATE",
                (rs, rowNum) -> rs.getLong("id"), scheduleId, tenantId, userId);
        if (rows.isEmpty()) {
            throw ServiceExceptionUtil.exception0(404, "个人日程不存在或不属于当前用户");
        }
    }

    private void validateFinalConflict(Long userId, Map<String, Object> draft, Long excludedScheduleId) {
        if (Boolean.TRUE.equals(draft.get("allowConflictOverride"))) return;
        LocalDateTime start = parseTime(draft.get("startTime"));
        LocalDateTime end = parseTime(draft.get("endTime"));
        PersonalScheduleCalendarReqVO request = new PersonalScheduleCalendarReqVO()
                .setStartTime(start).setEndTime(end);
        boolean personal = personalScheduleService.getMyCalendarList(userId, request).stream()
                .anyMatch(item -> !Objects.equals(item.getId(), excludedScheduleId));
        boolean booking = meetingBookingService.getMyCalendarList(userId, start, end).stream()
                .anyMatch(Objects::nonNull);
        if (personal || booking) {
            throw ServiceExceptionUtil.exception0(409,
                    "PERSONAL_SCHEDULE_CONFLICT：该时段与现有日程或会议预约冲突，请调整时间或明确确认冲突");
        }
    }

    private PersonalScheduleSaveReqVO saveRequest(Map<String, Object> draft, Long id) {
        PersonalScheduleSaveReqVO request = new PersonalScheduleSaveReqVO().setId(id)
                .setTitle(required(draft, "title"))
                .setStartTime(parseTime(draft.get("startTime")))
                .setEndTime(parseTime(draft.get("endTime")))
                .setLocation(nullable(draft.get("location")))
                .setDescription(nullable(draft.get("description")))
                .setOtherParticipants(nullable(draft.get("otherParticipants")));
        Object ids = draft.get("attendeeUserIds");
        if (ids instanceof List) {
            request.setAttendeeUserIds(((List<?>) ids).stream().filter(Objects::nonNull)
                    .map(x -> Long.valueOf(String.valueOf(x))).distinct().collect(Collectors.toList()));
        }
        return request;
    }

    private String version(PersonalScheduleDO source) {
        return source.getUpdateTime() == null ? "" : TIME.format(source.getUpdateTime());
    }

    private LocalDateTime parseTime(Object value) {
        try {
            return LocalDateTime.parse(String.valueOf(value).replace('T', ' '), TIME);
        } catch (Exception e) {
            throw ServiceExceptionUtil.exception0(400, "日程时间格式必须为 yyyy-MM-dd HH:mm:ss");
        }
    }

    private String required(Map<String, Object> value, String key) {
        String result = nullable(value.get(key));
        if (result == null) throw ServiceExceptionUtil.exception0(400, "缺少 " + key);
        return result;
    }

    private String nullable(Object value) {
        String result = value == null ? null : String.valueOf(value).trim();
        return result == null || result.isEmpty() || "null".equalsIgnoreCase(result) ? null : result;
    }

    private Long number(Object value) {
        try {
            String text = nullable(value);
            return text == null ? null : Long.valueOf(text);
        } catch (NumberFormatException e) {
            throw ServiceExceptionUtil.exception0(400, "sourceScheduleId 必须是数字");
        }
    }
}
