package cn.iocoder.yudao.server.service.agent;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 将单次 Run 的已脱敏事件投影为真实执行拓扑。
 *
 * <p>这里不创建架构模板节点，也不从用户文本或模型消息推断事件。输入已经由
 * {@link AgentAnalyticsService#traceEvent(long, String, String, String)} 做过字段白名单投影，
 * 本类只负责给事件实例补充展示语义和实际顺序边。</p>
 */
public final class AgentRunTopologyProjector {

    private static final Set<String> HIDDEN_EVENT_TYPES = new HashSet<>(Collections.singletonList("ui.metric"));

    private static final Map<String, String> LABELS = labels();

    private AgentRunTopologyProjector() {
    }

    /** 返回 version=3 的单 Run 拓扑；nodes 和 edges 均只来自该 Run 的观测事件。 */
    public static Map<String, Object> project(String runId, List<Map<String, Object>> events) {
        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> edges = new ArrayList<>();
        String previousId = null;
        for (Map<String, Object> source : events == null ? Collections.<Map<String, Object>>emptyList() : events) {
            String type = text(source.get("type"));
            if (type.isEmpty() || HIDDEN_EVENT_TYPES.contains(type)) continue;
            long sequence = number(source.get("sequence"));
            String nodeId = "event-" + sequence;
            Map<String, Object> node = new LinkedHashMap<>();
            node.put("id", nodeId);
            node.put("eventType", type);
            node.put("label", LABELS.containsKey(type) ? LABELS.get(type) : type);
            node.put("group", group(type));
            node.put("sequence", sequence);
            node.put("time", source.get("time"));
            node.put("observed", true);
            node.put("executions", 1);
            node.put("runCount", 1);
            boolean failed = Boolean.FALSE.equals(source.get("success")) || type.contains("failed");
            node.put("failures", failed ? 1 : 0);
            node.put("failureRate", failed ? 1D : 0D);
            node.put("rateAvailable", true);
            node.put("metricLabel", "本次 Run 失败率");
            node.put("description", "单次 Run 的真实事件：" + type);
            copy(node, source, "domain", "actionId", "toolName", "subagentName", "success", "status",
                    "durationMs", "errorCode", "errorMessage", "text", "batchId", "stepId", "operationId");
            nodes.add(node);
            if (previousId != null) {
                Map<String, Object> edge = new LinkedHashMap<>();
                edge.put("id", previousId + "-" + nodeId);
                edge.put("source", previousId);
                edge.put("target", nodeId);
                edge.put("kind", edgeKind(type));
                edge.put("label", edgeLabel(type));
                edges.add(edge);
            }
            previousId = nodeId;
        }

        Map<String, Object> graph = new LinkedHashMap<>();
        graph.put("version", 3);
        graph.put("mode", "run");
        graph.put("runId", runId);
        graph.put("nodes", nodes);
        graph.put("edges", edges);
        return graph;
    }

    private static void copy(Map<String, Object> target, Map<String, Object> source, String... keys) {
        for (String key : keys) {
            Object value = source.get(key);
            if (value != null && !(value instanceof Map) && !(value instanceof List)) target.put(key, value);
        }
    }

    private static String group(String type) {
        if (type.startsWith("coordination.")) return "跨领域协调";
        if (type.startsWith("subagent.") || type.startsWith("tool.")) return "领域执行";
        if (type.startsWith("operation.") || type.startsWith("draft.") || type.startsWith("approval.")) {
            return "业务状态与确认";
        }
        if (type.equals("narration.upsert") || type.equals("agent.final_answer.upsert")) return "输出交付";
        if (type.startsWith("run.")) return "运行状态";
        return "主 Agent 编排";
    }

    private static String edgeKind(String type) {
        if (type.contains("failed")) return "failure";
        if (type.startsWith("coordination.step.")) return "parallel";
        if (type.startsWith("approval.") || type.endsWith("waiting_approval")) return "approval";
        if (type.equals("run.completed") || type.equals("run.cancelled") || type.equals("run.failed")
                || type.equals("agent.final_answer.upsert")) return "terminal";
        return "sequence";
    }

    private static String edgeLabel(String type) {
        if (type.contains("failed")) return "失败分支";
        if (type.startsWith("coordination.step.")) return "并行步骤";
        if (type.startsWith("approval.") || type.endsWith("waiting_approval")) return "确认边界";
        if (type.equals("agent.final_answer.upsert")) return "最终输出";
        return "下一事件";
    }

    private static String text(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private static long number(Object value) {
        return value instanceof Number ? ((Number) value).longValue() : 0L;
    }

    private static Map<String, String> labels() {
        Map<String, String> labels = new HashMap<>();
        labels.put("run.started", "请求进入");
        labels.put("run.completed", "运行完成");
        labels.put("run.failed", "运行失败");
        labels.put("run.cancelled", "运行取消");
        labels.put("route.selected", "领域路由");
        labels.put("plan.created", "计划形成");
        labels.put("plan.compiled", "计划编译");
        labels.put("subagent.started", "领域委派");
        labels.put("subagent.completed", "领域回执");
        labels.put("tool.started", "调用工具");
        labels.put("tool.completed", "工具完成");
        labels.put("tool.failed", "工具失败");
        labels.put("coordination.batch.created", "创建跨领域批次");
        labels.put("coordination.batch.started", "批次运行");
        labels.put("coordination.step.started", "并行步骤开始");
        labels.put("coordination.step.completed", "并行步骤完成");
        labels.put("coordination.step.failed", "并行步骤失败");
        labels.put("coordination.step.waiting_approval", "步骤等待确认");
        labels.put("draft.created", "生成业务草稿");
        labels.put("approval.waiting", "等待人工确认");
        labels.put("approval.approved", "确认通过");
        labels.put("approval.rejected", "确认拒绝");
        labels.put("operation.committing", "提交业务效果");
        labels.put("operation.succeeded", "业务提交成功");
        labels.put("narration.upsert", "过程摘要");
        labels.put("agent.final_answer.upsert", "最终回答");
        return labels;
    }
}
