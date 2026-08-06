package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentActionCatalogRegistry;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Transport adapter for the Java-owned Agent action contract.
 *
 * <p>Action definitions live in {@link AgentActionCatalogRegistry}; this
 * controller intentionally contains no business-action table so the same
 * contract can be tested and reused by non-HTTP callers.</p>
 */
@Tag(name = "Business Agent Action Contract")
@RestController
public class AgentActionCatalogController {

    private final AgentActionCatalogRegistry registry;

    public AgentActionCatalogController(AgentActionCatalogRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/agent/config/actions")
    @Operation(summary = "读取 Agent 业务动作契约")
    public Map<String, Object> actions() {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("contractVersion", registry.contractVersion());
        response.put("actions", registry.actions());
        return response;
    }
}
