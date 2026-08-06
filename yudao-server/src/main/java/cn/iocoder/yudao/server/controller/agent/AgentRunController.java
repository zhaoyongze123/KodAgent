package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentRunEventService;
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

@Tag(name = "Business Agent Runs")
@RestController
@RequestMapping("/agent/runs")
public class AgentRunController {

    @Resource
    private AgentRunEventService agentRunEventService;

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
