package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentModelService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/** 模型供应商后台管理和 Python Agent 内部解析入口。 */
@Tag(name = "Agent Model Providers")
@RestController
public class AgentModelConfigController {
    @Resource private AgentModelService service;

    @GetMapping("/admin-api/agent/model-providers")
    @Operation(summary = "查询 Agent 模型供应商")
    public List<Map<String,Object>> providers() { return service.listProviders(getTenantId()); }

    @PostMapping("/admin-api/agent/model-providers")
    @Operation(summary = "保存 Agent 模型供应商")
    public Map<String,Object> save(@RequestBody Map<String,Object> request) { return service.saveProvider(getTenantId(), request); }

    @DeleteMapping("/admin-api/agent/model-providers/{providerId}")
    @Operation(summary = "停用 Agent 模型供应商")
    public void delete(@PathVariable Long providerId) { service.deleteProvider(getTenantId(), providerId); }

    @PostMapping("/admin-api/agent/model-providers/{providerId}/test")
    @Operation(summary = "测试模型供应商连接")
    public Map<String,Object> test(@PathVariable Long providerId) { return service.testProvider(getTenantId(), providerId); }

    @PostMapping("/admin-api/agent/model-providers/{providerId}/sync-models")
    @Operation(summary = "同步供应商模型")
    public Map<String,Object> sync(@PathVariable Long providerId) { return service.syncModels(getTenantId(), providerId); }

    @GetMapping("/admin-api/agent/models")
    @Operation(summary = "查询可用 Agent 模型")
    public List<Map<String,Object>> models(@RequestParam(required = false) Long providerId) { return service.listModels(getTenantId(), providerId); }

    @GetMapping("/admin-api/agent/model-bindings")
    @Operation(summary = "查询 Agent 默认模型绑定")
    public List<Map<String,Object>> bindings() { return service.listBindings(getTenantId()); }

    @PostMapping("/admin-api/agent/model-bindings")
    @Operation(summary = "保存 Agent 默认模型绑定")
    public Map<String,Object> saveBinding(@RequestBody Map<String,Object> request) { return service.saveBinding(getTenantId(), request); }

    @DeleteMapping("/admin-api/agent/model-bindings/{bindingId}")
    @Operation(summary = "删除 Agent 默认模型绑定")
    public void deleteBinding(@PathVariable Long bindingId) { service.deleteBinding(getTenantId(), bindingId); }

    @PutMapping("/admin-api/agent/models/{modelId}/capabilities")
    @Operation(summary = "更新 Agent 模型能力")
    public Map<String,Object> capabilities(@PathVariable Long modelId, @RequestBody Map<String,Object> request) {
        return service.updateCapabilities(getTenantId(), modelId, request);
    }

    @GetMapping("/agent/config/models/{modelId}")
    @Operation(summary = "解析本次 Agent Run 的模型配置")
    public Map<String,Object> resolve(@PathVariable Long modelId) { return service.resolve(getTenantId(), getLoginUserId(), modelId); }

    @GetMapping("/agent/config/resolve")
    @Operation(summary = "按当前用户和 Agent 绑定解析模型")
    public Map<String,Object> resolveDefault(@RequestParam(required = false) Long modelId,
                                              @RequestParam(required = false, defaultValue = "oa-main-agent") String agentName) {
        return service.resolveForRun(getTenantId(), getLoginUserId(), modelId, agentName);
    }

    @GetMapping("/agent/config/models")
    @Operation(summary = "查询当前用户可选择的 Agent 模型")
    public List<Map<String,Object>> availableModels() { return service.listModels(getTenantId(), null); }
}
