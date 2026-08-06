package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.enums.BpmnVariableConstants;
import cn.iocoder.yudao.module.bpm.service.task.BpmTaskService;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.ApprovalBatchExecuteResponse;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.ApprovalBatchItemResult;
import org.flowable.task.api.Task;
import org.flowable.task.api.history.HistoricTaskInstance;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Reconciles one atomic batch against the BPM facts after a cross-database
 * response was lost.
 *
 * <p>This is deliberately a batch-specific adapter, not a child-effect
 * runtime. The business operation is still one MySQL transaction. We only
 * need to prove whether every target reached the requested terminal state
 * before marking the single durable preview completed.</p>
 */
@Service
public class AgentApprovalBatchReconciliationService {

    @Resource
    private BpmTaskService taskService;

    @Resource
    private AgentApprovalBatchPreviewService previewService;

    @SuppressWarnings("unchecked")
    public Map<String, Object> reconcile(Long tenantId, Long userId, String previewId,
                                         String confirmationToken, String operationId,
                                         String idempotencyKey) {
        Map<String, Object> preview = previewService.get(tenantId, userId, previewId);
        requireEquals(operationId, preview.get("operationId"),
                "AGENT_APPROVAL_BATCH_OPERATION_MISMATCH：批量审批与当前 Operation 不匹配");
        requireEquals(confirmationToken, preview.get("confirmationToken"),
                "AGENT_APPROVAL_BATCH_TOKEN_INVALID：确认令牌无效");

        String status = String.valueOf(preview.get("status"));
        if ("COMPLETED".equals(status)) {
            return state(previewId, operationId, status, preview.get("result"), null);
        }
        if ("FAILED".equals(status)) {
            return state(previewId, operationId, "FAILED_FINAL", preview.get("result"),
                    "批量审批结果已确定失败，请人工核对");
        }
        if (!"EXECUTING".equals(status)) {
            return state(previewId, operationId, status, null,
                    "批量审批当前不在可恢复执行状态");
        }

        Map<String, Object> data = preview.get("preview") instanceof Map
                ? (Map<String, Object>) preview.get("preview") : Collections.emptyMap();
        String action = String.valueOf(data.getOrDefault("action", "")).toUpperCase(Locale.ROOT);
        List<String> taskIds = taskIds(data.get("taskIds"));
        List<ApprovalBatchItemResult> results = new ArrayList<>();
        boolean hasSuccess = false;
        boolean hasPending = false;
        boolean hasUnknown = false;
        boolean hasFailure = false;
        for (String taskId : taskIds) {
            Observation observation = observe(taskId, action);
            ApprovalBatchItemResult item = new ApprovalBatchItemResult();
            item.setTaskId(taskId);
            item.setStatus(observation.status);
            item.setMessage(observation.message);
            results.add(item);
            hasSuccess |= "SUCCESS".equals(observation.status);
            hasPending |= "PENDING".equals(observation.status);
            hasUnknown |= "UNKNOWN".equals(observation.status);
            hasFailure |= "FAILED".equals(observation.status);
        }

        if (hasFailure) {
            String resultStatus = hasSuccess || hasPending || hasUnknown
                    ? "INCONSISTENT" : "FAILED_FINAL";
            ApprovalBatchExecuteResponse response = new ApprovalBatchExecuteResponse();
            response.setPreviewId(previewId);
            response.setAction(action);
            response.setSuccess(false);
            response.setIdempotentReplay(true);
            response.setResults(results);
            previewService.fail(tenantId, userId, previewId, idempotencyKey, response);
            Map<String, Object> failed = previewService.get(tenantId, userId, previewId);
            return state(previewId, operationId, resultStatus, failed.get("result"),
                    "批量审批结果存在未能证明的混合状态，请人工核对后再处理");
        }
        if (hasPending || hasUnknown) {
            return state(previewId, operationId, hasPending ? "PENDING" : "UNKNOWN",
                    resultData(previewId, action, false, results),
                    "批量审批外部结果尚未全部可见");
        }

        ApprovalBatchExecuteResponse response = new ApprovalBatchExecuteResponse();
        response.setPreviewId(previewId);
        response.setAction(action);
        response.setSuccess(true);
        response.setIdempotentReplay(true);
        response.setResults(results);
        previewService.complete(tenantId, userId, previewId, idempotencyKey, response);
        Map<String, Object> completed = previewService.get(tenantId, userId, previewId);
        return state(previewId, operationId, "COMPLETED", completed.get("result"),
                "批量审批已根据 BPM 历史状态恢复");
    }

    private Observation observe(String taskId, String action) {
        Task active = taskService.getTask(taskId);
        if (active != null) {
            return new Observation("PENDING", "待办仍在处理中");
        }
        HistoricTaskInstance historic = taskService.getHistoricTask(taskId);
        if (historic == null || historic.getEndTime() == null) {
            return new Observation("UNKNOWN", "无法确认待办最终状态");
        }
        Object rawStatus = historic.getTaskLocalVariables() == null ? null
                : historic.getTaskLocalVariables().get(BpmnVariableConstants.TASK_VARIABLE_STATUS);
        Integer taskStatus = rawStatus instanceof Number ? ((Number) rawStatus).intValue() : null;
        boolean matched = "APPROVE".equals(action)
                ? BpmTaskStatusEnum.APPROVE.getStatus().equals(taskStatus)
                || BpmTaskStatusEnum.APPROVING.getStatus().equals(taskStatus)
                : "REJECT".equals(action) && BpmTaskStatusEnum.REJECT.getStatus().equals(taskStatus);
        return matched
                ? new Observation("SUCCESS", "审批动作已完成")
                : new Observation("FAILED", "待办最终状态与原批量动作不一致");
    }

    private List<String> taskIds(Object value) {
        if (!(value instanceof List)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BATCH_DATA_INVALID：批量审批预览缺少任务列表");
        }
        List<String> ids = new ArrayList<>();
        for (Object item : (List<?>) value) {
            if (item != null && !String.valueOf(item).trim().isEmpty()) {
                ids.add(String.valueOf(item).trim());
            }
        }
        if (ids.isEmpty() || ids.size() > 20 || ids.size() != new java.util.LinkedHashSet<>(ids).size()) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_BATCH_DATA_INVALID：批量审批预览任务列表无效");
        }
        return ids;
    }

    private Map<String, Object> resultData(String previewId, String action, boolean success,
                                            List<ApprovalBatchItemResult> results) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("previewId", previewId);
        result.put("action", action);
        result.put("success", success);
        result.put("results", results);
        return result;
    }

    private Map<String, Object> state(String previewId, String operationId, String status,
                                      Object result, String message) {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("previewId", previewId);
        state.put("operationId", operationId);
        state.put("status", status);
        if (result != null) state.put("result", result);
        if (message != null) state.put("message", message);
        return state;
    }

    private void requireEquals(String expected, Object actual, String message) {
        if (expected == null || expected.trim().isEmpty() || !expected.equals(String.valueOf(actual))) {
            throw ServiceExceptionUtil.exception0(409, message);
        }
    }

    private static final class Observation {
        private final String status;
        private final String message;

        private Observation(String status, String message) {
            this.status = status;
            this.message = message;
        }
    }
}
