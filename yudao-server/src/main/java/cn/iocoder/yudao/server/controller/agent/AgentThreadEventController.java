package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentRunEventService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/** Agent Thread 过程事件读取入口。写入仍只允许通过 Run 事件接口。 */
@Tag(name = "Business Agent Threads")
@RestController
@RequestMapping("/agent/threads")
public class AgentThreadEventController {

    @Resource
    private AgentRunEventService agentRunEventService;

    @GetMapping("/{threadId}/events")
    @Operation(summary = "按 Thread 读取 Agent 过程事件")
    public List<Map<String, Object>> listThreadEvents(
            @PathVariable String threadId,
            @RequestParam(value = "afterCursor", required = false) Long afterCursor,
            @RequestParam(value = "afterEventTime", required = false) String afterEventTime,
            @RequestParam(value = "afterEventId", defaultValue = "0") long afterEventId,
            @RequestParam(value = "limit", defaultValue = "1000") int limit) {
        return agentRunEventService.listByThread(getLoginUserId(), getTenantId(), threadId,
                afterCursor, afterEventTime, afterEventId, limit);
    }
}
