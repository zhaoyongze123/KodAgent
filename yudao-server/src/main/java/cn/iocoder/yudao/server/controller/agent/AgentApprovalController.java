package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentApprovalService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

@Tag(name = "Business Agent Approvals")
@RestController
@RequestMapping("/agent/approvals")
public class AgentApprovalController {

    @Resource
    private AgentApprovalService agentApprovalService;

    @GetMapping("/{approvalId}")
    @Operation(summary = "读取 Agent 审批状态")
    public Map<String, Object> get(@PathVariable String approvalId) {
        return agentApprovalService.get(getTenantId(), getLoginUserId(), approvalId);
    }

    @GetMapping("/{approvalId}/pending-card")
    @Operation(summary = "精确读取当前待审批卡片")
    public Map<String, Object> getPendingCard(@PathVariable String approvalId) {
        return agentApprovalService.getPendingCard(getTenantId(), getLoginUserId(), approvalId);
    }

    @GetMapping("/pending-card/by-draft/{draftId}")
    @Operation(summary = "按草稿精确读取当前待审批卡片")
    public Map<String, Object> getPendingCardByDraft(@PathVariable String draftId) {
        return agentApprovalService.getPendingCardByDraft(getTenantId(), getLoginUserId(), draftId);
    }

    @PostMapping("/{approvalId}/approve")
    @Operation(summary = "批准 Agent 审批")
    public Map<String, Object> approve(@PathVariable String approvalId,
                                        @RequestBody Map<String, Object> request) {
        return agentApprovalService.approve(getTenantId(), getLoginUserId(), approvalId,
                request.get("idempotencyKey") == null ? null
                        : String.valueOf(request.get("idempotencyKey")));
    }

    @PostMapping("/{approvalId}/reject")
    @Operation(summary = "拒绝 Agent 审批")
    public Map<String, Object> reject(@PathVariable String approvalId,
                                       @RequestBody Map<String, Object> request) {
        return agentApprovalService.reject(getTenantId(), getLoginUserId(), approvalId,
                request.get("idempotencyKey") == null ? null
                        : String.valueOf(request.get("idempotencyKey")),
                request.get("reason") == null ? null : String.valueOf(request.get("reason")));
    }

    @PostMapping("/{approvalId}/resume")
    @Operation(summary = "记录 Agent resume 幂等请求")
    public Map<String, Object> resume(@PathVariable String approvalId,
                                      @RequestBody Map<String, Object> request) {
        return agentApprovalService.recordResume(getTenantId(), getLoginUserId(), approvalId,
                request.get("idempotencyKey") == null ? null
                        : String.valueOf(request.get("idempotencyKey")));
    }
}
