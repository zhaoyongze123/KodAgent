package cn.iocoder.yudao.server.service.agent;

import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 项目进度的确定性统计服务。
 *
 * <p>模型不参与数字计算。所有完成、逾期、无负责人和停滞结论都从项目插件
 * 返回的结构化事实中计算，报告和聊天卡片共同使用本类的结果。</p>
 */
@Service
public class AgentProjectAnalysisService {

    private static final long SEVEN_DAYS = 7L * 24 * 60 * 60;
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /** 根据项目快照生成统一分析结果。 */
    public Map<String, Object> analyze(Map<String, Object> snapshot) {
        Map<String, Object> result = new LinkedHashMap<>();
        Map<String, Object> project = map(snapshot.get("project"));
        Map<String, Object> config = map(snapshot.get("config"));
        List<Map<String, Object>> tasks = new ArrayList<>();
        flatten(list(snapshot.get("tasks")), tasks);
        // 快照接口把任务放在 taskSummary 旁边，单独任务接口使用 tasks 字段。
        if (tasks.isEmpty()) flatten(list(snapshot.get("taskList")), tasks);
        List<Map<String, Object>> workItems = new ArrayList<>();
        for (Map<String, Object> task : tasks) {
            if (number(task.get("status"), 1) != 1 || number(task.get("isList"), 0) == 1) continue;
            List<?> children = list(task.get("children"));
            // 父任务只作为层级容器，不重复计入末级完成率。
            if (!children.isEmpty()) continue;
            workItems.add(task);
        }
        long now = System.currentTimeMillis() / 1000L;
        String finishType = text(config.get("taskFinishType"), "taskCheck");
        int completed = 0;
        int overdue = 0;
        int withoutOwner = 0;
        List<Map<String, Object>> risks = new ArrayList<>();
        Map<String, Map<String, Object>> ownerStats = new LinkedHashMap<>();
        Map<String, Long> latestActivity = latestActivity(snapshot.get("activity"));
        for (Map<String, Object> task : workItems) {
            boolean done = finished(task, config, finishType);
            String taskId = text(task.get("taskID"), "");
            String owner = text(task.get("ownerUser"), "");
            String ownerLabel = ownerName(snapshot.get("members"), owner);
            Map<String, Object> ownerStat = ownerStats.computeIfAbsent(owner,
                    ignored -> new LinkedHashMap<>());
            ownerStat.put("userID", owner);
            ownerStat.put("name", ownerLabel);
            increment(ownerStat, "assigned");
            if (done) {
                completed++;
                increment(ownerStat, "completed");
                continue;
            }
            long deadline = timestamp(task.get("timeTo"));
            if (deadline == 0) deadline = timestamp(map(task.get("metaInfo")).get("timeTo"));
            boolean isOverdue = deadline > 0 && deadline < now;
            if (isOverdue) {
                overdue++;
                increment(ownerStat, "overdue");
                risks.add(risk("HIGH", "OVERDUE", task, "任务已超过截止时间"));
            }
            if (owner.isEmpty()) {
                withoutOwner++;
                risks.add(risk("MEDIUM", "WITHOUT_OWNER", task, "任务没有负责人"));
            }
            long activity = Math.max(timestamp(task.get("modifyTime")), latestActivity.getOrDefault(taskId, 0L));
            // 没有任何日志或修改记录同样属于“近期无活动”，不能因为时间戳为空
            // 就把数据缺口误判成正常状态。
            if (activity == 0 || now - activity > SEVEN_DAYS) {
                risks.add(risk("MEDIUM", "STALE", task, "任务近 7 天没有修改或日志活动"));
            }
        }
        if ("taskNone".equals(finishType)) {
            risks.add(dataGap("项目未启用任务完成口径，无法计算完成率"));
        }
        Map<String, Object> kpis = new LinkedHashMap<>();
        kpis.put("total", workItems.size());
        kpis.put("completed", completed);
        kpis.put("incomplete", workItems.size() - completed);
        kpis.put("overdue", overdue);
        kpis.put("withoutOwner", withoutOwner);
        kpis.put("completionRate", workItems.isEmpty() || "taskNone".equals(finishType)
                ? null : round((double) completed / workItems.size(), 4));
        kpis.put("manualProgress", config.get("progress"));
        kpis.put("timeFrom", config.get("timeFrom"));
        kpis.put("timeTo", config.get("timeTo"));
        kpis.put("asOf", now);
        result.put("project", project);
        // 手工进度与系统完成率并列返回，报告层不得用其中一个覆盖另一个。
        result.put("projectConfig", config);
        result.put("kpis", kpis);
        // Excel 明细与聊天卡片共用同一批当前用户可见任务，不能在导出层另查一次。
        result.put("tasks", workItems);
        result.put("members", new ArrayList<>(ownerStats.values()));
        result.put("risks", risks.stream().sorted(Comparator.comparing(item -> severityOrder(text(item.get("severity"), "LOW")))).toList());
        result.put("activity", list(snapshot.get("activity")));
        result.put("documents", list(snapshot.get("documents")));
        List<String> gaps = dataGaps(risks);
        if (config.get("progress") == null) gaps.add("项目未配置手工进度");
        if (config.get("timeFrom") == null || config.get("timeTo") == null) gaps.add("项目时间范围不完整");
        result.put("dataGaps", gaps);
        result.put("methodology", List.of(
                "有效任务只统计正常状态、非列表分组的末级任务",
                "完成状态按项目 taskFinishType 判断",
                "没有截止时间的任务不判定为逾期",
                "索引和历史候选不是事实源，权限以 KodCloud 项目插件实时结果为准"
        ));
        return result;
    }

    private static List<String> dataGaps(List<Map<String, Object>> risks) {
        List<String> result = new ArrayList<>();
        for (Map<String, Object> item : risks) if ("DATA_GAP".equals(item.get("type"))) result.add(text(item.get("message"), ""));
        return result;
    }

    private static Map<String, Object> risk(String severity, String type, Map<String, Object> task, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("severity", severity); result.put("type", type); result.put("taskID", task.get("taskID"));
        result.put("taskName", text(task.get("name"), "未命名任务")); result.put("message", message);
        return result;
    }

    private static Map<String, Object> dataGap(String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("severity", "LOW"); result.put("type", "DATA_GAP"); result.put("message", message);
        return result;
    }

    private static int severityOrder(String value) { return "HIGH".equals(value) ? 0 : "MEDIUM".equals(value) ? 1 : 2; }

    private static Map<String, Long> latestActivity(Object raw) {
        Map<String, Long> result = new LinkedHashMap<>();
        for (Map<String, Object> item : list(raw)) {
            String taskId = text(item.get("taskID"), "");
            long time = Math.max(timestamp(item.get("createdAt")), timestamp(item.get("createTime")));
            if (!taskId.isEmpty()) result.put(taskId, Math.max(result.getOrDefault(taskId, 0L), time));
        }
        return result;
    }

    private static boolean finished(Map<String, Object> task, Map<String, Object> config, String type) {
        Map<String, Object> meta = map(task.get("metaInfo"));
        if ("taskCheck".equals(type)) return "1".equals(text(meta.get("taskCheck"), ""));
        if ("taskStatus".equals(type)) return "finished".equals(text(meta.get("taskStatus"), ""));
        if ("taskBug".equals(type)) return "closed".equals(text(meta.get("taskStatus"), ""));
        if ("taskDiy".equals(type)) {
            for (Map<String, Object> value : list(config.get("taskFinishDiy"))) {
                if ("finished".equals(text(value.get("type"), ""))
                        && text(value.get("id"), "").equals(text(meta.get("taskStatus"), ""))) return true;
            }
        }
        return false;
    }

    private static String ownerName(Object members, String id) {
        for (Map<String, Object> member : list(members)) {
            if (id.equals(text(member.get("userID"), ""))) return text(member.get("name"), id);
        }
        return id.isEmpty() ? "未指定" : "用户 " + id;
    }

    private static void increment(Map<String, Object> values, String key) {
        values.put(key, number(values.get(key), 0) + 1);
    }

    private static void flatten(List<Map<String, Object>> source, List<Map<String, Object>> target) {
        for (Map<String, Object> item : source) {
            target.add(item);
            flatten(list(item.get("children")), target);
        }
    }

    @SuppressWarnings("unchecked") private static Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }
    @SuppressWarnings("unchecked") private static List<Map<String, Object>> list(Object value) {
        if (!(value instanceof List)) return new ArrayList<>();
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : (List<?>) value) if (item instanceof Map) result.add((Map<String, Object>) item);
        return result;
    }
    private static String text(Object value, String fallback) { return value == null ? fallback : String.valueOf(value); }
    private static int number(Object value, int fallback) { try { return value == null ? fallback : Integer.parseInt(String.valueOf(value)); } catch (NumberFormatException ex) { return fallback; } }
    private static long timestamp(Object value) {
        if (value == null) return 0;
        if (value instanceof Number) return ((Number) value).longValue() > 10_000_000_000L ? ((Number) value).longValue() / 1000L : ((Number) value).longValue();
        String text = String.valueOf(value).trim();
        try { return Long.parseLong(text); } catch (NumberFormatException ignored) { }
        try { return LocalDateTime.parse(text.replace('T', ' '), TIME).atZone(ZoneId.systemDefault()).toEpochSecond(); } catch (RuntimeException ignored) { return 0; }
    }
    private static double round(double value, int scale) { double factor = Math.pow(10, scale); return Math.round(value * factor) / factor; }
}
