package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Agent 运行事件事实源。
 *
 * <p>Python 传入的 sequence 只作为兼容字段保留，不能作为排序依据。PostgreSQL
 * 在同一个 Thread 的事务锁内分配 durable cursor，查询和 Redis Outbox 都使用这个
 * cursor，保证并发事件可以稳定重放。</p>
 */
@Service
public class AgentRunEventService {

    /** 管理员追踪保留用户原话的最大长度；不保存系统提示、模型推理或工具结果。 */
    private static final int USER_PROMPT_MAX_LENGTH = 8192;

    @Resource
    private StringRedisTemplate stringRedisTemplate;

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void ensureSchema() {
        // 只校验部署迁移是否已执行，绝不在业务请求中创建表。
        jdbcTemplate.execute("SELECT 1 FROM agent_run LIMIT 0");
        jdbcTemplate.execute("SELECT 1 FROM agent_run_event LIMIT 0");
        jdbcTemplate.execute("SELECT 1 FROM agent_run_event_outbox LIMIT 0");
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> append(Long userId, Long tenantId, String runId,
                                      Map<String, Object> inputEvent) {
        Map<String, Object> event = new LinkedHashMap<>(inputEvent == null
                ? new LinkedHashMap<>() : inputEvent);
        validateEnvelope(userId, tenantId, runId, event);

        // 只锁定当前租户/用户/Thread：同一对话内的多个 Run/并行事件按事务提交
        // 顺序分配 durable cursor；不同用户和 Thread 可以并行写入，不会被全局锁拖慢。
        String threadId = required(event, "threadId");
        lockThread(tenantId, userId, threadId);

        String eventId = required(event, "eventId");
        if (eventId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "eventId 无效：最长 128 个字符");
        }
        StoredEvent existing = findByEventId(eventId);
        if (existing != null) {
            validateScope(existing, userId, tenantId, runId, event);
            if ("narration.upsert".equals(required(event, "type"))) {
                StoredEvent updated = updateNarrationIfNewer(existing, event, userId, tenantId);
                return response(updated, false);
            }
            return response(existing, false);
        }

        String eventType = required(event, "type");
        PromptCapture promptCapture = extractPromptCapture(event, eventType);
        if ("narration.upsert".equals(eventType)) {
            validateNarration(event);
        }
        String eventTime = required(event, "timestamp");
        String messageId = nullable(event.get("messageId"));
        List<StoredEvent> inserted = jdbcTemplate.query(
                "INSERT INTO agent_run_event (event_id, run_id, thread_id, message_id, tenant_id, user_id, "
                        + "sequence_no, event_type, event_data, event_time) "
                        + "VALUES (?, ?, ?, ?, ?, ?, nextval('agent_run_event_cursor_seq'), ?, "
                        + "CAST(? AS jsonb), CAST(? AS timestamptz)) "
                        + "RETURNING id, event_id, run_id, thread_id, message_id, tenant_id, user_id, "
                        + "sequence_no, event_time, event_data::text",
                (rs, rowNum) -> storedEvent(rs.getLong("id"), rs.getString("event_id"),
                        rs.getString("run_id"), rs.getString("thread_id"), rs.getString("message_id"),
                        rs.getLong("tenant_id"), rs.getLong("user_id"), rs.getLong("sequence_no"),
                        rs.getObject("event_time").toString(), rs.getString("event_data")),
                eventId, runId, threadId, messageId, String.valueOf(tenantId), String.valueOf(userId), eventType,
                JsonUtils.toJsonString(event), eventTime);

        StoredEvent stored = inserted.get(0);
        Map<String, Object> canonical = JsonUtils.parseObject(stored.eventData, Map.class);
        if (canonical == null) canonical = new LinkedHashMap<>();
        canonical.put("tenantId", tenantId);
        canonical.put("userId", userId);
        canonical.put("sequence", stored.cursor);
        canonical.put("runSequence", stored.cursor);
        canonical.put("eventCursor", cursor(stored));
        String canonicalJson = JsonUtils.toJsonString(canonical);
        jdbcTemplate.update("UPDATE agent_run_event SET event_data = CAST(? AS jsonb) WHERE id = ?",
                canonicalJson, stored.databaseId);
        stored.eventData = canonicalJson;

        upsertRun(userId, tenantId, canonical, promptCapture);
        String streamKey = key(userId, runId);
        jdbcTemplate.update("INSERT INTO agent_run_event_outbox (event_id, stream_key, payload) "
                        + "VALUES (?, ?, CAST(? AS jsonb)) ON CONFLICT (event_id) DO NOTHING",
                eventId, streamKey, canonicalJson);
        registerOutboxDrainAfterCommit();
        return response(stored, true);
    }

    /**
     * Acquire a transaction-scoped lock for one logical conversation only.
     *
     * <p>The hash input includes the security scope as well as the Thread ID.
     * The lock is held only until the surrounding PostgreSQL transaction ends;
     * it is not a process-wide mutex. PostgreSQL's sequence still provides the
     * durable cursor, while this lock makes cursor allocation and event commit
     * order deterministic within one Thread.</p>
     */
    private void lockThread(Long tenantId, Long userId, String threadId) {
        String lockScope = tenantId + ":" + userId + ":" + threadId;
        jdbcTemplate.query("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                rs -> null, lockScope);
    }

    private void validateEnvelope(Long userId, Long tenantId, String runId,
                                  Map<String, Object> event) {
        if (event == null) throw ServiceExceptionUtil.exception0(400, "事件不能为空");
        if (runId == null || runId.trim().isEmpty() || runId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "runId 无效");
        }
        if (!runId.equals(String.valueOf(event.get("runId")))) {
            throw ServiceExceptionUtil.exception0(400, "事件 runId 不一致");
        }
        validateOptionalIdentity(event, "tenantId", tenantId);
        validateOptionalIdentity(event, "userId", userId);
    }

    private void validateOptionalIdentity(Map<String, Object> event, String field, Long expected) {
        Object value = event.get(field);
        if (value == null) return;
        try {
            if (!expected.equals(Long.valueOf(String.valueOf(value)))) {
                throw ServiceExceptionUtil.exception0(403, "事件身份范围不匹配：" + field);
            }
        } catch (NumberFormatException ex) {
            throw ServiceExceptionUtil.exception0(400, "事件字段格式无效：" + field);
        }
    }

    private StoredEvent findByEventId(String eventId) {
        List<StoredEvent> rows = jdbcTemplate.query(
                "SELECT id, event_id, run_id, thread_id, message_id, tenant_id, user_id, sequence_no, "
                        + "event_time, event_data::text FROM agent_run_event WHERE event_id = ?",
                (rs, rowNum) -> storedEvent(rs.getLong("id"), rs.getString("event_id"),
                        rs.getString("run_id"), rs.getString("thread_id"), rs.getString("message_id"),
                        rs.getLong("tenant_id"), rs.getLong("user_id"), rs.getLong("sequence_no"),
                        rs.getObject("event_time").toString(), rs.getString("event_data")), eventId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private void validateScope(StoredEvent existing, Long userId, Long tenantId,
                               String runId, Map<String, Object> event) {
        if (!tenantId.equals(existing.tenantId) || !userId.equals(existing.userId)
                || !runId.equals(existing.runId)
                || !required(event, "threadId").equals(existing.threadId)) {
            throw ServiceExceptionUtil.exception0(409,
                    "EVENT_ID_SCOPE_CONFLICT：事件 ID 已被其他运行或用户使用");
        }
    }

    private Map<String, Object> response(StoredEvent event, boolean created) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("accepted", true);
        result.put("created", created);
        result.put("eventId", event.eventId);
        result.put("eventCursor", cursor(event));
        Map<String, Object> canonical = JsonUtils.parseObject(event.eventData, Map.class);
        if (canonical != null) {
            canonical.put("eventId", event.eventId);
            canonical.put("eventCursor", cursor(event));
            result.put("event", canonical);
        }
        return result;
    }

    /**
     * The first implementation deliberately persists one complete narration
     * per report_progress call.  It nevertheless supports a future throttled
     * stream using the same entry/event ID: a higher revision replaces the
     * stored snapshot without allocating another cursor or timeline row.
     */
    private StoredEvent updateNarrationIfNewer(StoredEvent existing, Map<String, Object> incoming,
                                               Long userId, Long tenantId) {
        Map<String, Object> current = JsonUtils.parseObject(existing.eventData, Map.class);
        if (current == null || !"narration.upsert".equals(String.valueOf(current.get("type")))) {
            throw ServiceExceptionUtil.exception0(409, "EVENT_ID_TYPE_CONFLICT：事件 ID 已用于非播报事件");
        }
        validateNarration(incoming);
        String currentEntryId = required(current, "entryId");
        if (!currentEntryId.equals(required(incoming, "entryId"))) {
            throw ServiceExceptionUtil.exception0(409, "NARRATION_ENTRY_CONFLICT：播报身份不匹配");
        }
        long currentRevision = narrationRevision(current);
        long incomingRevision = narrationRevision(incoming);
        String currentStatus = String.valueOf(current.get("status"));
        String incomingStatus = String.valueOf(incoming.get("status"));
        if (("completed".equals(currentStatus) || "failed".equals(currentStatus))
                && "streaming".equals(incomingStatus)) {
            return existing;
        }
        if (incomingRevision <= currentRevision) return existing;

        Map<String, Object> canonical = new LinkedHashMap<>(incoming);
        canonical.put("eventId", existing.eventId);
        canonical.put("tenantId", tenantId);
        canonical.put("userId", userId);
        canonical.put("sequence", existing.cursor);
        canonical.put("runSequence", existing.cursor);
        canonical.put("eventCursor", cursor(existing));
        String canonicalJson = JsonUtils.toJsonString(canonical);
        String eventTime = required(incoming, "timestamp");
        jdbcTemplate.update("UPDATE agent_run_event SET event_data = CAST(? AS jsonb), "
                        + "event_time = CAST(? AS timestamptz) WHERE id = ?",
                canonicalJson, eventTime, existing.databaseId);
        existing.eventData = canonicalJson;
        existing.eventTime = eventTime;
        return existing;
    }

    private void validateNarration(Map<String, Object> event) {
        required(event, "entryId");
        if (narrationRevision(event) < 1) {
            throw ServiceExceptionUtil.exception0(400, "narration revision 必须大于 0");
        }
        String status = required(event, "status");
        if (!("streaming".equals(status) || "completed".equals(status) || "failed".equals(status))) {
            throw ServiceExceptionUtil.exception0(400, "narration status 无效");
        }
        String text = nullable(event.get("text"));
        if (text == null && event.get("data") instanceof Map) {
            text = nullable(((Map<?, ?>) event.get("data")).get("text"));
        }
        if (text == null) throw ServiceExceptionUtil.exception0(400, "narration text 不能为空");
    }

    private long narrationRevision(Map<String, Object> event) {
        Object value = event.get("revision");
        try {
            return value instanceof Number ? ((Number) value).longValue()
                    : Long.parseLong(String.valueOf(value));
        } catch (RuntimeException ex) {
            throw ServiceExceptionUtil.exception0(400, "narration revision 格式无效");
        }
    }

    private Map<String, Object> cursor(StoredEvent event) {
        Map<String, Object> cursor = new LinkedHashMap<>();
        cursor.put("cursor", event.cursor);
        cursor.put("eventId", event.eventId);
        cursor.put("databaseId", event.databaseId);
        cursor.put("eventTime", event.eventTime);
        return cursor;
    }

    public List<Map<String, Object>> list(Long userId, Long tenantId, String runId,
                                          Long afterCursor, String afterEventTime,
                                          long afterEventId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 1000));
        if (afterCursor == null && afterEventId > 0) afterCursor = afterEventId;
        String predicate;
        Object[] args;
        if (afterCursor != null) {
            predicate = "run_id = ? AND tenant_id = ? AND user_id = ? AND sequence_no > ? "
                    + "ORDER BY sequence_no LIMIT ?";
            args = new Object[]{runId, String.valueOf(tenantId), String.valueOf(userId), afterCursor, safeLimit};
        } else {
            predicate = "run_id = ? AND tenant_id = ? AND user_id = ? "
                    + "AND event_time > ? ORDER BY sequence_no LIMIT ?";
            args = new Object[]{runId, String.valueOf(tenantId), String.valueOf(userId),
                    parseAfterTime(afterEventTime), safeLimit};
        }
        return queryEvents(predicate, args);
    }

    public List<Map<String, Object>> listByThread(Long userId, Long tenantId, String threadId,
                                                   Long afterCursor, String afterEventTime,
                                                   long afterEventId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 2000));
        if (afterCursor == null && afterEventId > 0) afterCursor = afterEventId;
        String predicate;
        Object[] args;
        if (afterCursor != null) {
            predicate = "thread_id = ? AND tenant_id = ? AND user_id = ? AND sequence_no > ? "
                    + "ORDER BY sequence_no LIMIT ?";
            args = new Object[]{threadId, String.valueOf(tenantId), String.valueOf(userId), afterCursor, safeLimit};
        } else {
            predicate = "thread_id = ? AND tenant_id = ? AND user_id = ? "
                    + "AND event_time > ? ORDER BY sequence_no LIMIT ?";
            args = new Object[]{threadId, String.valueOf(tenantId), String.valueOf(userId),
                    parseAfterTime(afterEventTime), safeLimit};
        }
        return queryEvents(predicate, args);
    }

    private List<Map<String, Object>> queryEvents(String predicate, Object[] args) {
        return jdbcTemplate.query(
                "SELECT id, event_id, sequence_no, event_time, event_data::text FROM agent_run_event WHERE " + predicate,
                (rs, rowNum) -> {
                    Map<String, Object> event = JsonUtils.parseObject(rs.getString("event_data"), Map.class);
                    if (event == null) event = new LinkedHashMap<>();
                    StoredEvent stored = storedEvent(rs.getLong("id"), rs.getString("event_id"), null,
                            null, null, null, null, rs.getLong("sequence_no"),
                            rs.getObject("event_time").toString(), rs.getString("event_data"));
                    event.put("sequence", stored.cursor);
                    event.put("runSequence", stored.cursor);
                    event.put("eventCursor", cursor(stored));
                    return event;
                }, args);
    }

    /**
     * 将事件投影为运行终态，并在首次 ``run.created`` 时固定用户原始提问。
     *
     * 用户提问不是时间线事件详情：写入前已从 event_data 移除，避免 Redis/outbox
     * 或普通事件查询意外暴露正文。后续事件始终不能覆盖首次提问。
     */
    private void upsertRun(Long userId, Long tenantId, Map<String, Object> event,
                           PromptCapture promptCapture) {
        String runId = required(event, "runId");
        String threadId = required(event, "threadId");
        String eventType = required(event, "type");
        String eventTime = required(event, "timestamp");
        String messageId = nullable(event.get("messageId"));
        String status = runStatus(eventType);
        String completedAt = isTerminal(eventType) ? eventTime : null;
        Long durationMs = durationMs(event);
        long eventCursor = eventCursor(event);
        Map<?, ?> data = event.get("data") instanceof Map
                ? (Map<?, ?>) event.get("data") : new LinkedHashMap<>();
        String errorCode = nullable(data.get("code"));
        String errorMessage = nullable(data.get("message"));
        Map<String, Object> metadataMap = new LinkedHashMap<>();
        metadataMap.put("conversationId", nullable(event.get("conversationId")));
        metadataMap.put("taskId", nullable(event.get("taskId")));
        String metadata = JsonUtils.toJsonString(metadataMap);
        int affected = jdbcTemplate.update(
                "INSERT INTO agent_run (run_id, thread_id, message_id, tenant_id, user_id, status, "
                        + "started_at, completed_at, duration_ms, error_code, error_message, user_prompt, prompt_truncated, metadata, last_event_cursor) "
                        + "VALUES (?, ?, ?, ?, ?, ?, CAST(? AS timestamptz), CAST(? AS timestamptz), ?, ?, ?, ?, ?, CAST(? AS jsonb), ?) "
                        + "ON CONFLICT (run_id) DO UPDATE SET thread_id = agent_run.thread_id, "
                        + "message_id = COALESCE(agent_run.message_id, EXCLUDED.message_id), "
                        + "user_prompt = COALESCE(agent_run.user_prompt, EXCLUDED.user_prompt), "
                        + "prompt_truncated = CASE WHEN agent_run.user_prompt IS NULL THEN EXCLUDED.prompt_truncated "
                        + "ELSE agent_run.prompt_truncated END, "
                        + "status = CASE "
                        + "WHEN EXCLUDED.last_event_cursor <= COALESCE(agent_run.last_event_cursor, 0) "
                        + "THEN agent_run.status "
                        + "WHEN agent_run.status IN ('COMPLETED','FAILED','CANCELLED') THEN agent_run.status "
                        + "ELSE EXCLUDED.status END, "
                        + "completed_at = CASE "
                        + "WHEN EXCLUDED.last_event_cursor > COALESCE(agent_run.last_event_cursor, 0) "
                        + "AND EXCLUDED.status IN ('COMPLETED','FAILED','CANCELLED') "
                        + "AND agent_run.status NOT IN ('COMPLETED','FAILED','CANCELLED') "
                        + "THEN COALESCE(EXCLUDED.completed_at, agent_run.completed_at) "
                        + "ELSE agent_run.completed_at END, "
                        + "duration_ms = CASE "
                        + "WHEN EXCLUDED.last_event_cursor > COALESCE(agent_run.last_event_cursor, 0) "
                        + "AND EXCLUDED.status IN ('COMPLETED','FAILED','CANCELLED') "
                        + "AND agent_run.status NOT IN ('COMPLETED','FAILED','CANCELLED') "
                        + "THEN COALESCE(EXCLUDED.duration_ms, agent_run.duration_ms) "
                        + "ELSE agent_run.duration_ms END, "
                        + "error_code = CASE "
                        + "WHEN EXCLUDED.last_event_cursor > COALESCE(agent_run.last_event_cursor, 0) "
                        + "AND EXCLUDED.status = 'FAILED' "
                        + "AND agent_run.status NOT IN ('COMPLETED','FAILED','CANCELLED') "
                        + "THEN COALESCE(EXCLUDED.error_code, agent_run.error_code) "
                        + "ELSE agent_run.error_code END, "
                        + "error_message = CASE "
                        + "WHEN EXCLUDED.last_event_cursor > COALESCE(agent_run.last_event_cursor, 0) "
                        + "AND EXCLUDED.status = 'FAILED' "
                        + "AND agent_run.status NOT IN ('COMPLETED','FAILED','CANCELLED') "
                        + "THEN COALESCE(EXCLUDED.error_message, agent_run.error_message) "
                        + "ELSE agent_run.error_message END, "
                        + "last_event_cursor = GREATEST(COALESCE(agent_run.last_event_cursor, 0), EXCLUDED.last_event_cursor), "
                        + "updated_at = CURRENT_TIMESTAMP "
                        + "WHERE agent_run.tenant_id = EXCLUDED.tenant_id "
                        + "AND agent_run.user_id = EXCLUDED.user_id "
                        + "AND agent_run.thread_id = EXCLUDED.thread_id",
                runId, threadId, messageId, String.valueOf(tenantId), String.valueOf(userId), status,
                eventTime, completedAt, durationMs, errorCode, errorMessage,
                promptCapture.prompt, promptCapture.truncated, metadata, eventCursor);
        if (affected == 0) {
            throw ServiceExceptionUtil.exception0(409,
                    "RUN_SCOPE_CONFLICT：运行 ID 已绑定到其他租户、用户或 Thread");
        }
    }

    /**
     * 仅接收主图 ``run.created`` 事件携带的用户原始提问，并从事件 JSON 中删除正文。
     *
     * 这样 ``agent_run`` 是唯一的 Prompt 事实源；event_data、Redis outbox 和一般
     * 事件回放都不会包含用户正文。历史控制台使用的 userMessage 字段也兼容读取。
     */
    @SuppressWarnings("unchecked")
    private PromptCapture extractPromptCapture(Map<String, Object> event, String eventType) {
        if (!"run.created".equals(eventType) || !(event.get("data") instanceof Map)) {
            return PromptCapture.empty();
        }
        Map<String, Object> data = new LinkedHashMap<>((Map<String, Object>) event.get("data"));
        event.put("data", data);
        Object rawPrompt = data.remove("userPrompt");
        if (rawPrompt == null) rawPrompt = data.remove("userMessage");
        Object rawTruncated = data.remove("promptTruncated");
        if (rawPrompt == null) return PromptCapture.empty();
        String prompt = String.valueOf(rawPrompt).trim();
        if (prompt.isEmpty()) return PromptCapture.empty();
        boolean truncated = Boolean.TRUE.equals(rawTruncated) || prompt.length() > USER_PROMPT_MAX_LENGTH;
        if (prompt.length() > USER_PROMPT_MAX_LENGTH) {
            prompt = prompt.substring(0, USER_PROMPT_MAX_LENGTH);
        }
        return new PromptCapture(prompt, truncated);
    }

    /** 用户原始提问的受限投影，避免把 Event 数据对象传递到运行表投影层。 */
    private static final class PromptCapture {
        private final String prompt;
        private final boolean truncated;

        private PromptCapture(String prompt, boolean truncated) {
            this.prompt = prompt;
            this.truncated = truncated;
        }

        private static PromptCapture empty() {
            return new PromptCapture(null, false);
        }
    }

    private String runStatus(String eventType) {
        if ("run.paused".equals(eventType)) return "PAUSED";
        if ("run.resumed".equals(eventType)) return "RUNNING";
        if ("run.completed".equals(eventType)) return "COMPLETED";
        if ("run.failed".equals(eventType)) return "FAILED";
        if ("run.cancelled".equals(eventType)) return "CANCELLED";
        return "RUNNING";
    }

    private boolean isTerminal(String eventType) {
        return "run.completed".equals(eventType) || "run.failed".equals(eventType)
                || "run.cancelled".equals(eventType);
    }

    private Long durationMs(Map<String, Object> event) {
        Object value = event.get("durationMs");
        if (value == null && event.get("data") instanceof Map) value = ((Map<?, ?>) event.get("data")).get("durationMs");
        if (value instanceof Number) return ((Number) value).longValue();
        try { return value == null ? null : Long.parseLong(String.valueOf(value)); }
        catch (Exception ignored) { return null; }
    }

    private long eventCursor(Map<String, Object> event) {
        Object value = event.get("sequence");
        if (value == null) value = event.get("runSequence");
        if (value instanceof Number) return ((Number) value).longValue();
        try {
            return value == null ? 0L : Long.parseLong(String.valueOf(value));
        } catch (RuntimeException ex) {
            throw ServiceExceptionUtil.exception0(400, "事件 sequence 格式无效");
        }
    }

    private void registerOutboxDrainAfterCommit() {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            drainOutbox(100);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                drainOutbox(100);
            }
        });
    }

    @Scheduled(fixedDelayString = "${yudao.agent.events.outbox.retry-delay-ms:5000}")
    public void retryPendingEvents() { drainOutbox(200); }

    private void drainOutbox(int limit) {
        List<Map<String, Object>> pending;
        try {
            pending = jdbcTemplate.query(
                    "SELECT event_id, stream_key, payload::text FROM agent_run_event_outbox "
                            + "WHERE published_at IS NULL AND next_attempt_at <= CURRENT_TIMESTAMP "
                            + "ORDER BY created_at LIMIT ?",
                    (rs, rowNum) -> {
                        Map<String, Object> row = new LinkedHashMap<>();
                        row.put("eventId", rs.getString("event_id"));
                        row.put("streamKey", rs.getString("stream_key"));
                        row.put("payload", rs.getString("payload"));
                        return row;
                    }, limit);
        } catch (RuntimeException ignored) { return; }
        for (Map<String, Object> row : pending) {
            String eventId = String.valueOf(row.get("eventId"));
            try {
                String payload = String.valueOf(row.get("payload"));
                String streamKey = String.valueOf(row.get("streamKey"));
                Map<String, String> streamFields = new HashMap<>();
                streamFields.put("eventId", eventId);
                streamFields.put("payload", payload);
                stringRedisTemplate.opsForStream().add(StreamRecords.newRecord().in(streamKey).ofMap(streamFields));
                stringRedisTemplate.expire(streamKey, 7, TimeUnit.DAYS);
                Map<String, Object> event = JsonUtils.parseObject(payload, Map.class);
                if (event != null) {
                    String eventUserId = String.valueOf(event.get("userId"));
                    String threadId = String.valueOf(event.get("threadId"));
                    String runId = String.valueOf(event.get("runId"));
                    String indexKey = threadKey(Long.valueOf(eventUserId), threadId);
                    stringRedisTemplate.opsForSet().add(indexKey, runId);
                    stringRedisTemplate.expire(indexKey, 7, TimeUnit.DAYS);
                }
                jdbcTemplate.update("UPDATE agent_run_event_outbox SET published_at = CURRENT_TIMESTAMP "
                        + "WHERE event_id = ? AND published_at IS NULL", eventId);
            } catch (RuntimeException ex) {
                jdbcTemplate.update("UPDATE agent_run_event_outbox SET attempts = attempts + 1, last_error = ?, "
                                + "next_attempt_at = CURRENT_TIMESTAMP + (LEAST(attempts + 1, 8) * INTERVAL '5 seconds') "
                                + "WHERE event_id = ? AND published_at IS NULL",
                        truncate(ex.getMessage()), eventId);
            }
        }
    }

    private OffsetDateTime parseAfterTime(String value) {
        if (value == null || value.trim().isEmpty()) return OffsetDateTime.parse("1970-01-01T00:00:00Z");
        try { return OffsetDateTime.parse(value); }
        catch (RuntimeException ex) { throw ServiceExceptionUtil.exception0(400, "事件游标时间格式无效"); }
    }

    private String required(Map<String, Object> event, String name) {
        String value = nullable(event.get(name));
        if (value == null || value.trim().isEmpty()) throw ServiceExceptionUtil.exception0(400, "事件缺少字段：" + name);
        return value;
    }

    private String nullable(Object value) {
        if (value == null) return null;
        String text = String.valueOf(value);
        return text.trim().isEmpty() ? null : text;
    }

    private String truncate(String value) {
        if (value == null) return "unknown Redis outbox error";
        return value.length() <= 1000 ? value : value.substring(0, 1000);
    }

    private String key(Long userId, String runId) { return "agent:events:" + userId + ":" + runId; }

    private String threadKey(Long userId, String threadId) {
        return "agent:events:thread:" + userId + ":" + threadId;
    }

    private StoredEvent storedEvent(long id, String eventId, String runId, String threadId,
                                    String messageId, Long tenantId, Long userId, long cursor,
                                    String eventTime, String eventData) {
        StoredEvent result = new StoredEvent();
        result.databaseId = id;
        result.eventId = eventId;
        result.runId = runId;
        result.threadId = threadId;
        result.messageId = messageId;
        result.tenantId = tenantId;
        result.userId = userId;
        result.cursor = cursor;
        result.eventTime = eventTime;
        result.eventData = eventData;
        return result;
    }

    private static class StoredEvent {
        private long databaseId;
        private String eventId;
        private String runId;
        private String threadId;
        private String messageId;
        private Long tenantId;
        private Long userId;
        private long cursor;
        private String eventTime;
        private String eventData;
    }
}
