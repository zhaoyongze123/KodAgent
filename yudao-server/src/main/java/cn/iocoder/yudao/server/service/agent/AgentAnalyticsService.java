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
        response.put("executionGraph", executionGraph(summary, tenant, since));
        response.put("coordination", coordination);
        response.put("modelTelemetry", modelTelemetry());
        return response;
    }

    /**
     * 将运行事实投影成可交互的执行架构拓扑。
     *
     * <p>拓扑结构（节点、分支和泳道）是代码所定义的运行架构；节点指标只来自
     * {@code agent_run}、{@code agent_run_event} 和协调批次表。两者刻意分离：即使某个
     * 新功能尚无线上样本，前端仍能看见它在架构中的位置，但不会把不存在的失败事件显示为 0%。</p>
     *
     * <p>返回的 {@code version=2} 契约使用 {@code nodes + edges}，供流程图组件缩放、拖拽和
     * hover 明细使用。旧版仅有节点数组的消费方需要改读 {@code executionGraph.nodes}。</p>
     *
     * @param summary 当前时间窗内的 Run 终态聚合
     * @param tenant 当前管理员租户，来自身份上下文而非浏览器参数
     * @param since 统计窗口起点，所有事件节点必须使用同一个窗口
     */
    private Map<String, Object> executionGraph(Map<String, Object> summary, String tenant, OffsetDateTime since) {
        Map<String, EventMetric> eventMetrics = eventMetrics(tenant, since);
        Map<String, Long> failures = graphFailureMetrics(tenant, since);
        EventMetric coordination = coordinationMetric(tenant, since);

        List<Map<String, Object>> nodes = new ArrayList<>();
        nodes.add(executionNode("run_input", "请求进入", "主 Agent 编排",
                "一次用户请求对应一个 Run；运行表是终态和耗时的唯一事实源。",
                Arrays.asList("run.started", "run.completed", "run.failed", "run.cancelled"),
                eventMetric(summary, "total_runs"), count(summary, "failed_runs"), true, "运行失败"));
        nodes.add(eventNode("route", "领域路由", "主 Agent 编排",
                "识别领域、动作和续办策略。当前没有 route.failed 事件生产者，因此只展示被记录的路由次数。",
                "route.selected", eventMetrics, null, false, "路由错误未持久化"));
        nodes.add(eventNode("plan_created", "计划形成", "主 Agent 编排",
                "将路由结果形成可校验的候选计划。", "plan.created", eventMetrics, null, false, "计划创建"));
        nodes.add(eventNode("compiler", "计划编译", "主 Agent 编排",
                "把领域动作编译为确定性 WorkOrder；仅 UNSUPPORTED 表示未注册动作，不把澄清请求记作故障。",
                "plan.compiled", eventMetrics, failures.get("compiler"), true, "未注册动作"));
        nodes.add(eventNode("subagent", "领域子 Agent", "领域执行",
                "子 Agent 只执行中央编译后的 WorkOrder，并可调用执行契约允许的只读 helper。",
                "subagent.started", eventMetrics, failures.get("subagent"), true, "委派失败"));
        nodes.add(eventNode("tool", "领域工具", "领域执行",
                "领域工具读取业务事实、生成草稿或执行已确认的业务操作。", "tool.started", eventMetrics,
                failures.get("tool"), true, "工具失败"));
        nodes.add(eventNode("workflow", "宏工作流", "工作流与业务状态",
                "需要多步骤编排的业务流程。workflow.failed 与 workflow.started 可形成可验证失败率。",
                "workflow.started", eventMetrics, failures.get("workflow"), true, "工作流失败"));
        nodes.add(eventNode("workflow_node", "工作流节点", "工作流与业务状态",
                "工作流内部的确定性节点。当前失败事件只记录在 workflow.failed，未归属到具体节点。",
                "workflow.node.started", eventMetrics, null, false, "节点失败未持久化"));
        nodes.add(eventNode("operation", "业务 Operation", "工作流与业务状态",
                "跨 Run 可恢复的业务状态机，从收集信息、运行到最终提交均由 Operation 保存。",
                "operation.collecting_info", eventMetrics, failures.get("operation"), true, "Operation 失败"));
        nodes.add(eventNode("draft", "生成草稿", "人工确认",
                "写操作先生成业务草稿，草稿不是最终提交。", "draft.created", eventMetrics, null, false, "草稿生成"));
        nodes.add(eventNode("approval_wait", "等待人工确认", "人工确认",
                "Run 暂停或 Operation 进入 WAITING_APPROVAL；这是业务等待状态，不是执行失败。",
                "operation.waiting_approval", eventMetrics, null, false, "待确认"));
        nodes.add(eventNode("approval_approved", "确认通过", "人工确认",
                "用户在官方确认卡完成确认后才允许进入提交阶段。", "approval.approved", eventMetrics,
                null, false, "确认通过"));
        nodes.add(eventNode("approval_rejected", "确认拒绝", "人工确认",
                "用户拒绝草稿属于业务选择，不计为 Agent 执行失败。", "approval.rejected", eventMetrics,
                null, false, "确认拒绝"));
        nodes.add(eventNode("operation_commit", "提交业务效果", "工作流与业务状态",
                "确认后的 Effect 提交阶段，具有幂等和恢复语义。", "operation.committing", eventMetrics,
                null, false, "提交中"));
        nodes.add(eventNode("operation_succeeded", "业务提交成功", "工作流与业务状态",
                "Operation 的已提交终态；它不等价于整个对话 Run 的完成。", "operation.succeeded", eventMetrics,
                null, false, "业务成功"));
        nodes.add(executionNode("coordination_batch", "跨领域批次", "跨领域协调",
                "中央编译器创建的多领域批次；状态由 coordination_batch 表保存，支持进程重启后的继续执行。",
                Arrays.asList("coordination.batch.created", "coordination.batch.started", "coordination.batch.succeeded", "coordination.batch.failed"),
                coordination, coordination.failures, true, "批次失败"));
        nodes.add(eventNode("coordination_step", "跨领域步骤", "跨领域协调",
                "可并行的领域步骤，每项都携带不可变 WorkOrder 并由对应子 Agent 执行。",
                "coordination.step.started", eventMetrics, failures.get("coordination_step"), true, "步骤失败"));
        nodes.add(eventNode("coordination_wait", "批次等待确认", "跨领域协调",
                "任一步骤等待人工确认时，批次暂停，后续依赖步骤不会越过确认边界。",
                "coordination.step.waiting_approval", eventMetrics, null, false, "等待确认"));
        nodes.add(eventNode("coordination_succeeded", "批次汇总成功", "跨领域协调",
                "所有可执行步骤汇总后的成功终态。", "coordination.batch.succeeded", eventMetrics,
                null, false, "批次成功"));
        nodes.add(eventNode("coordination_failed", "批次汇总失败", "跨领域协调",
                "批次进入 FAILED 终态；PARTIAL_SUCCEEDED 会保留在批次明细中，不混作失败。",
                "coordination.batch.failed", eventMetrics, null, false, "批次失败"));
        nodes.add(executionNode("run_completed", "运行完成", "运行终态",
                "主 Agent 已完成本次 Run。", Arrays.asList("run.completed"),
                eventMetric(summary, "completed_runs"), null, false, "完成运行"));
        nodes.add(executionNode("run_failed", "运行失败", "运行终态",
                "Run 被运行时标记为 FAILED；具体错误可在失败追踪抽屉定位。", Arrays.asList("run.failed"),
                eventMetric(summary, "failed_runs"), null, false, "失败运行"));
        nodes.add(executionNode("run_cancelled", "运行取消", "运行终态",
                "用户或业务流程取消本次 Run。", Arrays.asList("run.cancelled"),
                eventMetric(summary, "cancelled_runs"), null, false, "取消运行"));

        Map<String, Object> graph = new LinkedHashMap<>();
        graph.put("version", 2);
        graph.put("nodes", nodes);
        graph.put("edges", executionEdges());
        return graph;
    }

    /** 读取同一统计窗口的事件次数和关联 Run 数，不从聊天文本或模型输出推断执行状态。 */
    private Map<String, EventMetric> eventMetrics(String tenant, OffsetDateTime since) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT event_type, COUNT(*) AS executions, COUNT(DISTINCT NULLIF(run_id, '')) AS run_count "
                        + "FROM agent_run_event WHERE tenant_id = ? AND event_time >= ? GROUP BY event_type",
                tenant, since);
        Map<String, EventMetric> metrics = new LinkedHashMap<>();
        for (Map<String, Object> row : rows) {
            metrics.put(String.valueOf(row.get("event_type")), new EventMetric(
                    count(row, "executions"), count(row, "run_count")));
        }
        return metrics;
    }

    /**
     * 读取可证明的阶段失败数。每一项都与对应节点的真实开始事件成对出现；没有这种
     * 事件契约的节点必须返回 rateAvailable=false，不能以 0 替代未知。
     */
    private Map<String, Long> graphFailureMetrics(String tenant, OffsetDateTime since) {
        Map<String, Object> row = jdbcTemplate.queryForMap(
                "SELECT "
                        + "COUNT(*) FILTER (WHERE event_type = 'plan.compiled' "
                        + "AND event_data #>> '{data,planStatus}' = 'UNSUPPORTED') AS compiler, "
                        + "COUNT(*) FILTER (WHERE event_type = 'subagent.completed' "
                        + "AND event_data #>> '{data,success}' = 'false') AS subagent, "
                        + "COUNT(*) FILTER (WHERE event_type = 'tool.failed') AS tool, "
                        + "COUNT(*) FILTER (WHERE event_type = 'workflow.failed') AS workflow, "
                        + "COUNT(*) FILTER (WHERE event_type IN ('operation.failed', 'operation.unknown')) AS operation, "
                        + "COUNT(*) FILTER (WHERE event_type = 'coordination.step.failed') AS coordination_step "
                        + "FROM agent_run_event WHERE tenant_id = ? AND event_time >= ?",
                tenant, since);
        Map<String, Long> failures = new LinkedHashMap<>();
        for (String key : Arrays.asList("compiler", "subagent", "tool", "workflow", "operation", "coordination_step")) {
            failures.put(key, count(row, key));
        }
        return failures;
    }

    /** 读取跨领域批次的当前持久化状态，补足事件流尚未覆盖的重启恢复和终态事实。 */
    private EventMetric coordinationMetric(String tenant, OffsetDateTime since) {
        Map<String, Object> row = jdbcTemplate.queryForMap(
                "SELECT COUNT(*) AS executions, COUNT(DISTINCT NULLIF(current_run_id, '')) AS run_count, "
                        + "COUNT(*) FILTER (WHERE status = 'FAILED') AS failures "
                        + "FROM agent_runtime.coordination_batch WHERE tenant_id = ? AND updated_at >= ?",
                tenant, since);
        return new EventMetric(count(row, "executions"), count(row, "run_count"), count(row, "failures"));
    }

    /** 基于单一事件节点构造指标；其 eventTypes 同时是 hover 中展示的数据依据。 */
    private Map<String, Object> eventNode(String id, String label, String group, String description,
                                          String eventType, Map<String, EventMetric> metrics,
                                          Long failures, boolean rateAvailable, String metricLabel) {
        return executionNode(id, label, group, description, Arrays.asList(eventType),
                metrics.getOrDefault(eventType, EventMetric.ZERO), failures, rateAvailable, metricLabel);
    }

    /** 生成前端流程图节点；未知失败率始终以 null 表示，避免把没有观测能力误报成健康。 */
    private Map<String, Object> executionNode(String id, String label, String group, String description,
                                              List<String> eventTypes, EventMetric metric, Long failures,
                                              boolean rateAvailable, String metricLabel) {
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("id", id);
        node.put("label", label);
        node.put("group", group);
        node.put("description", description);
        node.put("eventTypes", eventTypes);
        node.put("executions", metric.executions);
        node.put("runCount", metric.runCount);
        node.put("failures", rateAvailable ? (failures == null ? 0L : failures) : null);
        node.put("failureRate", rateAvailable && metric.executions > 0
                ? (double) (failures == null ? 0L : failures) / metric.executions : null);
        node.put("rateAvailable", rateAvailable);
        node.put("metricLabel", metricLabel);
        return node;
    }

    /** 固定架构边而非按单次 Run 猜测顺序，kind 让前端能区分主线、分支、并行和终态。 */
    private List<Map<String, Object>> executionEdges() {
        List<Map<String, Object>> edges = new ArrayList<>();
        addEdge(edges, "input-route", "run_input", "route", "进入路由", "primary");
        addEdge(edges, "route-plan", "route", "plan_created", "形成计划", "primary");
        addEdge(edges, "plan-compiler", "plan_created", "compiler", "编译工单", "primary");
        addEdge(edges, "compiler-subagent", "compiler", "subagent", "单领域委派", "primary");
        addEdge(edges, "compiler-coordination", "compiler", "coordination_batch", "多领域批次", "parallel");
        addEdge(edges, "compiler-completed", "compiler", "run_completed", "只读或澄清结束", "branch");
        addEdge(edges, "subagent-tool", "subagent", "tool", "调用领域工具", "primary");
        addEdge(edges, "tool-workflow", "tool", "workflow", "进入宏工作流", "branch");
        addEdge(edges, "tool-operation", "tool", "operation", "直接业务操作", "primary");
        addEdge(edges, "tool-failed", "tool", "run_failed", "工具失败", "failure");
        addEdge(edges, "workflow-node", "workflow", "workflow_node", "执行内部节点", "primary");
        addEdge(edges, "workflow-operation", "workflow_node", "operation", "更新业务状态", "primary");
        addEdge(edges, "workflow-wait", "workflow", "approval_wait", "等待确认", "branch");
        addEdge(edges, "workflow-failed", "workflow", "run_failed", "工作流失败", "failure");
        addEdge(edges, "operation-draft", "operation", "draft", "生成写操作草稿", "branch");
        addEdge(edges, "operation-failed", "operation", "run_failed", "业务状态失败", "failure");
        addEdge(edges, "draft-wait", "draft", "approval_wait", "暂停并展示确认卡", "primary");
        addEdge(edges, "wait-approved", "approval_wait", "approval_approved", "用户确认", "primary");
        addEdge(edges, "wait-rejected", "approval_wait", "approval_rejected", "用户拒绝", "branch");
        addEdge(edges, "approved-commit", "approval_approved", "operation_commit", "允许提交", "primary");
        addEdge(edges, "commit-succeeded", "operation_commit", "operation_succeeded", "primary", "primary");
        addEdge(edges, "operation-completed", "operation_succeeded", "run_completed", "汇总响应", "terminal");
        addEdge(edges, "rejected-completed", "approval_rejected", "run_completed", "结束本次确认", "terminal");
        addEdge(edges, "coordination-step", "coordination_batch", "coordination_step", "并行派发步骤", "parallel");
        addEdge(edges, "coordination-subagent", "coordination_step", "subagent", "按领域委派", "parallel");
        addEdge(edges, "coordination-wait", "coordination_step", "coordination_wait", "任一步骤待确认", "branch");
        addEdge(edges, "coordination-wait-hitl", "coordination_wait", "approval_wait", "进入确认卡", "branch");
        addEdge(edges, "coordination-success", "coordination_step", "coordination_succeeded", "汇总成功", "primary");
        addEdge(edges, "coordination-failed", "coordination_step", "coordination_failed", "步骤失败", "failure");
        addEdge(edges, "coordination-completed", "coordination_succeeded", "run_completed", "汇总结果", "terminal");
        addEdge(edges, "coordination-run-failed", "coordination_failed", "run_failed", "批次失败", "terminal");
        return edges;
    }

    /** 加入一条由前端渲染的静态架构边。 */
    private void addEdge(List<Map<String, Object>> edges, String id, String source, String target,
                         String label, String kind) {
        Map<String, Object> edge = new LinkedHashMap<>();
        edge.put("id", id);
        edge.put("source", source);
        edge.put("target", target);
        edge.put("label", label);
        edge.put("kind", kind);
        edges.add(edge);
    }

    /** 事件聚合的小型值对象；三参构造用于协调批次表的失败数读取。 */
    private static final class EventMetric {
        private static final EventMetric ZERO = new EventMetric(0L, 0L);
        private final long executions;
        private final long runCount;
        private final long failures;

        private EventMetric(long executions, long runCount) {
            this(executions, runCount, 0L);
        }

        private EventMetric(long executions, long runCount, long failures) {
            this.executions = executions;
            this.runCount = runCount;
            this.failures = failures;
        }
    }

    /** 将运行表的计数包装为节点指标，运行数与执行次数在 Run 终态节点上相同。 */
    private EventMetric eventMetric(Map<String, Object> source, String key) {
        long value = count(source, key);
        return new EventMetric(value, value);
    }

    /** JDBC 聚合结果可能是 Long、Integer 或 BigDecimal，统一转换以避免强转脆弱性。 */
    private long count(Map<String, Object> source, String key) {
        Object value = source.get(key);
        return value instanceof Number ? ((Number) value).longValue() : 0L;
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
     * 返回一个 Run 的安全追踪时间线。所有字段都通过 allowlist 投影，避免把工具参数、
     * 业务返回体、隐藏思考或确认令牌带到管理员页面。
     */
    public Map<String, Object> runTrace(Long tenantId, String runId) {
        if (runId == null || runId.trim().isEmpty() || runId.length() > 128) {
            throw ServiceExceptionUtil.exception0(400, "runId 无效");
        }
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT run_id, status, started_at, completed_at, duration_ms, error_code, error_message "
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
                "success", "status", "durationMs", "errorCode", "strategy", "confidence");
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
