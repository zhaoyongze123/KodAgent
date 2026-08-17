package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.LinkedHashSet;

/**
 * Agent 管理员运行台的只读统计与追踪服务。
 *
 * <p>本类只从 PostgreSQL 运行事实表读取数据：{@code agent_run} 保存一次运行的终态，
 * {@code agent_run_event} 保存按数据库游标排序的阶段事件，协调批次状态来自 Python
 * Runtime 表。绝不从聊天正文、浏览器缓存或模型推理内容反推指标。</p>
 *
 * <p>该服务面向管理员全院视图。权限由 Controller 入口的
 * {@code agent:analytics:read} 契约控制，查询方法本身不接受 userId，避免前端伪造
 * 用户编号改变统计范围。</p>
 */
@Service
public class AgentAnalyticsService {

    private static final Set<String> RUN_STATUSES = new LinkedHashSet<>(Arrays.asList(
            "RUNNING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"));

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    /**
     * 返回管理员运行台的概览、趋势、漏斗和可优化信号。
     *
     * @param tenantId 当前身份所属租户，始终由 Java 身份上下文提供
     * @param days 回看天数，限制为 1 到 90
     * @param granularity 趋势颗粒度，仅允许 hour 或 day
     */
    public Map<String, Object> overview(Long tenantId, int days, String granularity) {
        int safeDays = safeDays(days);
        OffsetDateTime since = OffsetDateTime.now(ZoneOffset.UTC).minusDays(safeDays);
        String tenant = String.valueOf(tenantId);
        boolean hourly = "hour".equalsIgnoreCase(granularity) && safeDays <= 7;

        Map<String, Object> summary = jdbcTemplate.queryForMap(
                "SELECT COUNT(*) AS total_runs, "
                        + "COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed_runs, "
                        + "COUNT(*) FILTER (WHERE status = 'FAILED') AS failed_runs, "
                        + "COUNT(*) FILTER (WHERE status = 'CANCELLED') AS cancelled_runs, "
                        + "COUNT(*) FILTER (WHERE status = 'PAUSED') AS waiting_approval_runs, "
                        + "COUNT(*) FILTER (WHERE status = 'RUNNING') AS active_runs, "
                        + "COALESCE(ROUND(AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL)), 0) AS avg_duration_ms, "
                        + "COALESCE(ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) "
                        + "FILTER (WHERE duration_ms IS NOT NULL)), 0) AS p95_duration_ms "
                        + "FROM agent_run WHERE tenant_id = ? AND started_at >= ?",
                tenant, since);

        String bucket = hourly
                ? "to_char(date_trunc('hour', started_at AT TIME ZONE 'Asia/Shanghai'), 'MM-DD HH24:00')"
                : "to_char(date_trunc('day', started_at AT TIME ZONE 'Asia/Shanghai'), 'MM-DD')";
        String bucketOrder = hourly
                ? "date_trunc('hour', started_at AT TIME ZONE 'Asia/Shanghai')"
                : "date_trunc('day', started_at AT TIME ZONE 'Asia/Shanghai')";
        List<Map<String, Object>> trend = jdbcTemplate.queryForList(
                "SELECT " + bucket + " AS bucket, COUNT(*) AS total, "
                        + "COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed, "
                        + "COUNT(*) FILTER (WHERE status = 'FAILED') AS failed, "
                        + "COUNT(*) FILTER (WHERE status = 'PAUSED') AS waiting_approval "
                        + "FROM agent_run WHERE tenant_id = ? AND started_at >= ? "
                        + "GROUP BY " + bucketOrder + " ORDER BY " + bucketOrder,
                tenant, since);

        List<Map<String, Object>> failures = jdbcTemplate.queryForList(
                "SELECT COALESCE(NULLIF(error_code, ''), 'UNKNOWN') AS code, COUNT(*) AS count "
                        + "FROM agent_run WHERE tenant_id = ? AND started_at >= ? AND status = 'FAILED' "
                        + "GROUP BY COALESCE(NULLIF(error_code, ''), 'UNKNOWN') ORDER BY count DESC, code LIMIT 10",
                tenant, since);

        List<Map<String, Object>> domains = jdbcTemplate.queryForList(
                "SELECT COALESCE(NULLIF(e.event_data #>> '{data,domain}', ''), "
                        + "NULLIF(split_part(e.event_data #>> '{data,actionId}', '.', 1), ''), '未标记') AS domain, "
                        + "COUNT(DISTINCT e.run_id) AS runs, COUNT(*) AS events "
                        + "FROM agent_run_event e WHERE e.tenant_id = ? AND e.event_time >= ? "
                        + "AND (e.event_data #>> '{data,domain}' IS NOT NULL OR e.event_data #>> '{data,actionId}' IS NOT NULL) "
                        + "GROUP BY COALESCE(NULLIF(e.event_data #>> '{data,domain}', ''), "
                        + "NULLIF(split_part(e.event_data #>> '{data,actionId}', '.', 1), ''), '未标记') "
                        + "ORDER BY runs DESC, domain LIMIT 12",
                tenant, since);

        List<Map<String, Object>> funnel = jdbcTemplate.queryForList(
                "SELECT stage, COUNT(DISTINCT run_id) AS count FROM ("
                        + "SELECT run_id, 'routed' AS stage FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? AND event_type = 'route.selected' "
                        + "UNION ALL SELECT run_id, 'compiled' FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? AND event_type = 'plan.compiled' "
                        + "UNION ALL SELECT run_id, 'delegated' FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? AND event_type = 'subagent.started' "
                        + "UNION ALL SELECT run_id, 'completed' FROM agent_run WHERE tenant_id = ? AND started_at >= ? AND status = 'COMPLETED' "
                        + ") stages GROUP BY stage",
                tenant, since, tenant, since, tenant, since, tenant, since);

        List<Map<String, Object>> tools = jdbcTemplate.queryForList(
                "SELECT COALESCE(NULLIF(event_data #>> '{data,toolName}', ''), '未标记工具') AS tool_name, "
                        + "COUNT(*) FILTER (WHERE event_type = 'tool.started') AS started, "
                        + "COUNT(*) FILTER (WHERE event_type = 'tool.completed') AS completed, "
                        + "COUNT(*) FILTER (WHERE event_type = 'tool.failed') AS failed, "
                        // durationMs 属于统一事件信封顶层；data 只存阶段补充字段。
                        // 这里必须与 Python build_event 的结构一致，不能从 data 里猜测耗时。
                        + "COALESCE(ROUND(AVG(CASE WHEN event_data #>> '{durationMs}' ~ '^[0-9]+$' "
                        + "THEN (event_data #>> '{durationMs}')::numeric END)), 0) AS avg_duration_ms "
                        + "FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? "
                        + "AND event_type IN ('tool.started', 'tool.completed', 'tool.failed') "
                        + "GROUP BY COALESCE(NULLIF(event_data #>> '{data,toolName}', ''), '未标记工具') "
                        + "ORDER BY failed DESC, completed DESC, tool_name LIMIT 10",
                tenant, since);

        List<Map<String, Object>> qualitySignals = jdbcTemplate.queryForList(
                "SELECT signal, COUNT(*) AS count FROM ("
                        + "SELECT '编译澄清' AS signal FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? "
                        // Python 路由事件使用 planStatus 记录编译器输出，不能误读为通用 status。
                        + "AND event_type = 'plan.compiled' AND event_data #>> '{data,planStatus}' = 'CLARIFY' "
                        + "UNION ALL SELECT '未注册动作' FROM agent_run WHERE tenant_id = ? AND started_at >= ? AND error_code = 'UNSUPPORTED' "
                        + "UNION ALL SELECT '工具失败' FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? AND event_type = 'tool.failed' "
                        + "UNION ALL SELECT '等待确认' FROM agent_run WHERE tenant_id = ? AND started_at >= ? AND status = 'PAUSED' "
                        + ") signals GROUP BY signal ORDER BY count DESC, signal",
                tenant, since, tenant, since, tenant, since, tenant, since);

        List<Map<String, Object>> coordination = jdbcTemplate.queryForList(
                "SELECT status, COUNT(*) AS count FROM agent_runtime.coordination_batch "
                        + "WHERE tenant_id = ? AND updated_at >= ? GROUP BY status ORDER BY count DESC, status",
                tenant, since);

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("scope", "tenant_admin");
        response.put("days", safeDays);
        response.put("granularity", hourly ? "hour" : "day");
        response.put("since", since.toString());
        response.put("summary", summary);
        response.put("trend", trend);
        response.put("failures", failures);
        response.put("domains", domains);
        response.put("funnel", funnel);
        response.put("tools", tools);
        response.put("qualitySignals", qualitySignals);
        response.put("coordination", coordination);
        response.put("modelTelemetry", modelTelemetry());
        return response;
    }

    /**
     * 分页读取最近运行。列表只包含定位故障所需的摘要，不携带聊天正文或工具返回体。
     *
     * @param pageNo 从 1 开始的页码，超过有效范围时返回空列表而不是回退到最后一页
     * @param pageSize 每页数量，限制为 1 到 100，避免管理员页面一次拉取全院运行记录
     */
    public Map<String, Object> listRuns(Long tenantId, int days, String requestedStatus,
                                        String requestedDomain, int pageNo, int pageSize) {
        int safePageNo = Math.max(1, Math.min(pageNo, 10_000));
        int safePageSize = Math.max(1, Math.min(pageSize, 100));
        OffsetDateTime since = OffsetDateTime.now(ZoneOffset.UTC).minusDays(safeDays(days));
        String status = normalizeStatus(requestedStatus);
        String domain = normalizeDomain(requestedDomain);
        List<Object> args = new ArrayList<>();
        StringBuilder where = new StringBuilder("r.tenant_id = ? AND r.started_at >= ?");
        args.add(String.valueOf(tenantId));
        args.add(since);
        if (status != null) {
            where.append(" AND r.status = ?");
            args.add(status);
        }
        if (domain != null) {
            where.append(" AND EXISTS (SELECT 1 FROM agent_run_event domain_event WHERE domain_event.run_id = r.run_id "
                    + "AND domain_event.tenant_id = r.tenant_id AND COALESCE(NULLIF(domain_event.event_data #>> '{data,domain}', ''), "
                    + "NULLIF(split_part(domain_event.event_data #>> '{data,actionId}', '.', 1), '')) = ?)");
            args.add(domain);
        }
        Long total = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM agent_run r WHERE " + where, Long.class, args.toArray());
        long offset = (long) (safePageNo - 1) * safePageSize;
        args.add(safePageSize);
        args.add(offset);
        List<Map<String, Object>> runs = jdbcTemplate.query(
                "SELECT r.run_id, r.status, r.started_at, r.completed_at, r.duration_ms, r.error_code, r.error_message, "
                        + "COALESCE(context.domain, '未标记') AS domain, context.action_id, stage.last_stage, "
                        + "COALESCE(tool_failures.failed_tools, 0) AS failed_tools "
                        + "FROM agent_run r "
                        + "LEFT JOIN LATERAL (SELECT COALESCE(NULLIF(e.event_data #>> '{data,domain}', ''), "
                        + "NULLIF(split_part(e.event_data #>> '{data,actionId}', '.', 1), '')) AS domain, "
                        + "NULLIF(e.event_data #>> '{data,actionId}', '') AS action_id "
                        + "FROM agent_run_event e WHERE e.run_id = r.run_id AND e.tenant_id = r.tenant_id "
                        // 终态 run.completed 往往不带领域；这里取最近一次带领域或动作的业务事件，
                        // 不能让生命周期事件把表格中的领域事实覆盖成“未标记”。
                        + "AND (e.event_data #>> '{data,domain}' IS NOT NULL OR e.event_data #>> '{data,actionId}' IS NOT NULL) "
                        + "ORDER BY e.sequence_no DESC LIMIT 1) context ON TRUE "
                        // 最后阶段仍需要按全部事件读取，用于判断当前运行停在何处。
                        + "LEFT JOIN LATERAL (SELECT e.event_type AS last_stage FROM agent_run_event e "
                        + "WHERE e.run_id = r.run_id AND e.tenant_id = r.tenant_id "
                        + "ORDER BY e.sequence_no DESC LIMIT 1) stage ON TRUE "
                        + "LEFT JOIN LATERAL (SELECT COUNT(*) AS failed_tools FROM agent_run_event tool_event "
                        + "WHERE tool_event.run_id = r.run_id AND tool_event.tenant_id = r.tenant_id "
                        + "AND tool_event.event_type = 'tool.failed') tool_failures ON TRUE "
                        + "WHERE " + where + " ORDER BY r.started_at DESC LIMIT ? OFFSET ?",
                (rs, rowNum) -> runSummary(rs), args.toArray());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("items", runs);
        result.put("pageNo", safePageNo);
        result.put("pageSize", safePageSize);
        result.put("total", total == null ? 0 : total);
        result.put("since", since.toString());
        return result;
    }

    /**
     * 返回一个 Run 的安全追踪时间线。所有字段都通过 allowlist 投影；仅具有
     * agent:analytics:read 权限的调用方可看到该运行首次捕获的用户原始提问，
     * 不返回工具参数、业务返回体、隐藏思考或确认令牌。
     */
    public Map<String, Object> runTrace(Long tenantId, String runId) {
        if (runId == null || runId.trim().isEmpty() || runId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "runId 无效");
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT run_id, status, started_at, completed_at, duration_ms, error_code, error_message, "
                        + "user_prompt, prompt_truncated "
                        + "FROM agent_run WHERE run_id = ? AND tenant_id = ?", runId, String.valueOf(tenantId));
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(404, "运行记录不存在");
        Map<String, Object> run = new LinkedHashMap<>(rows.get(0));
        run.put("error_message", safeText(run.get("error_message"), 360));
        List<Map<String, Object>> events = jdbcTemplate.query(
                "SELECT sequence_no, event_type, event_time, event_data::text FROM agent_run_event "
                        + "WHERE run_id = ? AND tenant_id = ? ORDER BY sequence_no LIMIT 500",
                (rs, rowNum) -> traceEvent(rs.getLong("sequence_no"), rs.getString("event_type"),
                        rs.getObject("event_time").toString(), rs.getString("event_data")),
                runId, String.valueOf(tenantId));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("run", run);
        result.put("events", events);
        result.put("traceId", runId);
        result.put("prompt", run.remove("user_prompt"));
        result.put("promptTruncated", Boolean.TRUE.equals(run.remove("prompt_truncated")));
        result.put("executionGraph", AgentRunTopologyProjector.project(runId, events));
        return result;
    }

    private int safeDays(int days) {
        return Math.max(1, Math.min(days, 90));
    }

    private String normalizeStatus(String value) {
        if (value == null || value.trim().isEmpty() || "ALL".equalsIgnoreCase(value)) return null;
        String status = value.trim().toUpperCase();
        if (!RUN_STATUSES.contains(status)) throw ServiceExceptionUtil.exception0(400, "运行状态筛选无效");
        return status;
    }

    private String normalizeDomain(String value) {
        if (value == null || value.trim().isEmpty() || "ALL".equalsIgnoreCase(value)) return null;
        String domain = value.trim();
        if (domain.length() > 64 || !domain.matches("[A-Za-z0-9_.-]+")) {
            throw ServiceExceptionUtil.exception0(400, "领域筛选无效");
        }
        return domain;
    }

    private Map<String, Object> runSummary(java.sql.ResultSet rs) throws java.sql.SQLException {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("runId", rs.getString("run_id"));
        row.put("status", rs.getString("status"));
        row.put("startedAt", rs.getObject("started_at").toString());
        Object completed = rs.getObject("completed_at");
        row.put("completedAt", completed == null ? null : completed.toString());
        row.put("durationMs", rs.getObject("duration_ms"));
        row.put("errorCode", rs.getString("error_code"));
        row.put("errorMessage", safeText(rs.getString("error_message"), 180));
        row.put("domain", rs.getString("domain"));
        row.put("actionId", rs.getString("action_id"));
        row.put("lastStage", rs.getString("last_stage"));
        row.put("failedTools", rs.getLong("failed_tools"));
        return row;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> traceEvent(long sequence, String type, String time, String source) {
        Map<String, Object> raw = JsonUtils.parseObject(source, Map.class);
        Map<String, Object> data = raw != null && raw.get("data") instanceof Map
                ? (Map<String, Object>) raw.get("data") : new LinkedHashMap<>();
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("sequence", sequence);
        event.put("type", type);
        event.put("time", time);
        copySafe(event, data, "domain", "actionId", "capabilityId", "toolName", "subagentName",
                "success", "status", "durationMs", "errorCode", "strategy", "confidence",
                "batchId", "stepId", "operationId");
        String errorCode = firstText(data, "errorCode", "code");
        String errorMessage = firstText(data, "errorMessage", "message");
        String text = firstText(data, "summary", "text");
        if (errorCode != null) event.put("errorCode", errorCode);
        if (errorMessage != null) event.put("errorMessage", safeText(errorMessage, 360));
        if (text != null) event.put("text", safeText(text, 300));
        return event;
    }

    private void copySafe(Map<String, Object> target, Map<String, Object> source, String... keys) {
        for (String key : keys) {
            Object value = source.get(key);
            if (value != null && !(value instanceof Map) && !(value instanceof List)) target.put(key, value);
        }
    }

    private String firstText(Map<String, Object> data, String... keys) {
        for (String key : keys) {
            Object value = data.get(key);
            if (value != null && !String.valueOf(value).trim().isEmpty()) return String.valueOf(value);
        }
        return null;
    }

    private String safeText(Object source, int limit) {
        if (source == null) return null;
        String text = String.valueOf(source).replaceAll("(?i)(api[_-]?key|authorization|bearer)\\s*[:=]?\\s*\\S+", "$1=***");
        text = text.replaceAll("\\s+", " ").trim();
        return text.length() <= limit ? text : text.substring(0, limit) + "...";
    }

    private Map<String, Object> modelTelemetry() {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("available", false);
        state.put("message", "模型 Token、首 Token 耗时和费用尚未写入运行事件，面板不会展示推测值。");
        return state;
    }
}
