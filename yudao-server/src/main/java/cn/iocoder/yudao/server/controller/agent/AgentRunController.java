package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentRunEventService;
import cn.iocoder.yudao.server.service.agent.AgentAnalyticsService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Collections;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/**
 * Agent 运行事件、管理员运行台与取消操作的 HTTP 入口。
 *
 * <p>普通运行事件仍按当前用户写入和读取；统计相关接口由独立的管理员权限保护，
 * 只能读取服务端根据当前租户确定的范围，不能由浏览器传入用户编号扩大查询。</p>
 */
@Tag(name = "Business Agent Runs")
@RestController
@RequestMapping("/agent/runs")
public class AgentRunController {

    @Resource
    private AgentRunEventService agentRunEventService;

    @Resource
    private AgentAnalyticsService agentAnalyticsService;

    @GetMapping("/analytics/overview")
    @Operation(summary = "读取管理员 Agent 运行台概览")
    public Map<String, Object> analyticsOverview(
            @RequestParam(value = "days", defaultValue = "14") int days,
            @RequestParam(value = "granularity", defaultValue = "day") String granularity) {
        return agentAnalyticsService.overview(getTenantId(), days, granularity);
    }

    /** 管理员按状态和领域分页筛选最近运行，用于失败定位表格。 */
    @GetMapping("/analytics/runs")
    @Operation(summary = "读取管理员最近 Agent 运行列表")
    public Map<String, Object> analyticsRuns(
            @RequestParam(value = "days", defaultValue = "14") int days,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "domain", required = false) String domain,
            @RequestParam(value = "pageNo", defaultValue = "1") int pageNo,
            @RequestParam(value = "pageSize", defaultValue = "20") int pageSize) {
        return agentAnalyticsService.listRuns(getTenantId(), days, status, domain, pageNo, pageSize);
    }

    /** 管理员读取单次运行的 allowlist 追踪时间线，可查看已脱敏的用户提问，但不返回工具结果。 */
    @GetMapping("/analytics/runs/{runId}")
    @Operation(summary = "读取管理员 Agent 运行安全追踪")
    public Map<String, Object> analyticsRunTrace(@PathVariable String runId) {
        return agentAnalyticsService.runTrace(getTenantId(), runId);
    }

    @PostMapping("/{runId}/events")
    @Operation(summary = "保存 Agent 运行事件")
    public Map<String, Object> appendAgentEvent(@PathVariable String runId,
                                                 @RequestBody Map<String, Object> event) {
        return agentRunEventService.append(getLoginUserId(), getTenantId(), runId, event);
    }

    @PostMapping("/{runId}/cancel")
    @Operation(summary = "记录 Agent Run 已取消")
    public Map<String, Object> cancelAgentRun(@PathVariable String runId,
                                               @RequestBody Map<String, Object> request) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventId", "ui-cancelled-" + runId);
        event.put("runId", runId);
        event.put("threadId", String.valueOf(request.getOrDefault("threadId", "")));
        event.put("messageId", String.valueOf(request.getOrDefault("messageId", "")));
        event.put("sequence", 0);
        event.put("type", "run.cancelled");
        event.put("timestamp", OffsetDateTime.now().toString());
        event.put("data", Collections.singletonMap("source", "agent-ui"));
        return agentRunEventService.append(getLoginUserId(), getTenantId(), runId, event);
    }

    @PostMapping("/{runId}/metrics")
    @Operation(summary = "保存 Agent 前端运行指标")
    public Map<String, Object> appendMetric(@PathVariable String runId,
                                             @RequestBody Map<String, Object> request) {
        String metric = String.valueOf(request.getOrDefault("metric", "unknown"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("source", "agent-ui");
        data.put("metric", metric);
        data.put("value", request.getOrDefault("value", 0));
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventId", "ui-metric-" + runId + "-" + metric);
        event.put("runId", runId);
        event.put("threadId", String.valueOf(request.getOrDefault("threadId", "")));
        event.put("messageId", String.valueOf(request.getOrDefault("messageId", "")));
        event.put("sequence", 0);
        event.put("type", "ui.metric");
        event.put("timestamp", OffsetDateTime.now().toString());
        event.put("data", data);
        return agentRunEventService.append(getLoginUserId(), getTenantId(), runId, event);
    }

    @GetMapping("/{runId}/events")
    @Operation(summary = "读取 Agent 运行事件")
    public List<Map<String, Object>> listAgentEvents(@PathVariable String runId,
                                                      @RequestParam(value = "afterCursor", required = false) Long afterCursor,
                                                      @RequestParam(value = "afterEventTime", required = false) String afterEventTime,
                                                      @RequestParam(value = "afterEventId", defaultValue = "0") long afterEventId,
                                                      @RequestParam(value = "limit", defaultValue = "100") int limit) {
        return agentRunEventService.list(getLoginUserId(), getTenantId(), runId,
                afterCursor, afterEventTime, afterEventId, limit);
    }
}
