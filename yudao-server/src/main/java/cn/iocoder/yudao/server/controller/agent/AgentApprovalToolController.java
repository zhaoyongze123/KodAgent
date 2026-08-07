package cn.iocoder.yudao.server.controller.agent;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.util.date.DateUtils;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.process.BpmProcessDefinitionRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.instance.*;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.task.*;
import cn.iocoder.yudao.module.bpm.convert.task.BpmTaskConvert;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmProcessDefinitionInfoDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOATripDO;
import cn.iocoder.yudao.module.bpm.service.definition.BpmApprovalTemplateService;
import cn.iocoder.yudao.module.bpm.service.definition.BpmProcessDefinitionService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOALeaveService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOATripService;
import cn.iocoder.yudao.module.bpm.service.task.BpmProcessInstanceService;
import cn.iocoder.yudao.module.bpm.service.task.BpmTaskService;
import cn.iocoder.yudao.module.bpm.enums.definition.BpmSimpleModelNodeTypeEnum;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.enums.BpmnVariableConstants;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.util.BpmnModelUtils;
import cn.iocoder.yudao.module.system.api.dept.DeptApi;
import cn.iocoder.yudao.module.system.api.dept.dto.DeptRespDTO;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import cn.iocoder.yudao.module.system.api.user.dto.AdminUserRespDTO;
import cn.iocoder.yudao.server.service.agent.AgentApprovalInboxFilter;
import cn.iocoder.yudao.server.service.agent.AgentApprovalBatchPreviewService;
import cn.iocoder.yudao.server.service.agent.AgentApprovalBatchReconciliationService;
import cn.iocoder.yudao.server.service.agent.AgentApprovalBatchTestHook;
import cn.iocoder.yudao.server.service.agent.AgentApprovalService;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.flowable.engine.repository.ProcessDefinition;
import org.flowable.engine.history.HistoricProcessInstance;
import org.flowable.engine.runtime.ProcessInstance;
import org.flowable.task.api.Task;
import org.flowable.task.api.history.HistoricTaskInstance;
import org.flowable.bpmn.model.BpmnModel;
import org.flowable.bpmn.model.FlowElement;
import org.flowable.bpmn.model.SubProcess;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.convertSet;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

@Tag(name = "Business Agent Approval Tools")
@RestController
@RequestMapping("/agent/tools")
@Validated
public class AgentApprovalToolController {
    /** 第一阶段只接通有固定、受校验表单的 OA 请假和出差流程。 */
    private static final String LEAVE = "leave", TRIP = "trip";
    private static final String LEAVE_KEY = "oa_leave", TRIP_KEY = "oa_trip";
    /** Prevent one natural-language query from loading an unbounded BPM inbox. */
    private static final int APPROVAL_INBOX_SCAN_LIMIT = 100;
    private static final int APPROVAL_INBOX_EXCLUSION_LIMIT = 20;
    @Resource private BpmApprovalTemplateService approvalTemplateService;
    @Resource private BpmProcessInstanceService processInstanceService;
    @Resource private BpmTaskService taskService;
    @Resource private BpmProcessDefinitionService processDefinitionService;
    @Resource private BpmOALeaveService leaveService;
    @Resource private BpmOATripService tripService;
    @Resource private AdminUserApi adminUserApi;
    @Resource private DeptApi deptApi;
    @Resource private AgentApprovalBatchPreviewService approvalBatchPreviewService;
    @Resource private AgentApprovalBatchReconciliationService approvalBatchReconciliationService;
    @Resource private AgentApprovalBatchTestHook approvalBatchTestHook;
    @Resource private AgentApprovalService agentApprovalService;

    @GetMapping("/approvals/types")
    @Operation(summary = "列出当前用户可发起的审批模板")
    public ApprovalTypeListResponse listStartableApprovalTypes() {
        ApprovalTypeListResponse response = new ApprovalTypeListResponse();
        response.setTemplates(approvalTemplateService.getApprovalTemplateList(getLoginUserId()).stream()
                .map(item -> {
            ApprovalType result = new ApprovalType();
            // The template key is the stable business selector.  Leave/trip
            // keep their historic aliases; every other visible template is
            // now addressable by its own key instead of being hidden as
            // "unsupported".
            result.setRequestType(StrUtil.blankToDefault(item.getKey(), item.getId()));
            result.setProcessDefinitionId(item.getId());
            result.setProcessDefinitionName(item.getName()); result.setCategory(item.getCategoryName()); result.setDescription(item.getFormName());
            result.setFormFields(item.getFormFields() == null ? Collections.emptyList() : item.getFormFields());
            return result;
        }).collect(Collectors.toList()));
        return response;
    }

    /**
     * Preview any visible BPM template using only its declared form fields.
     * This is the generic counterpart of the legacy leave/trip preview and
     * keeps the model away from Flowable system variables and engine IDs.
     */
    @PostMapping("/approvals/generic/preview")
    @Operation(summary = "预览任意可发起审批模板")
    public Map<String, Object> previewGenericApproval(@Valid @RequestBody GenericApprovalPreviewRequest request) {
        BpmProcessDefinitionRespVO template = resolveVisibleTemplate(request.getProcessDefinition());
        Map<String, Object> variables = validateGenericVariables(template, request.getVariables(), request.getActivityId());
        BpmApprovalDetailReqVO detailReq = new BpmApprovalDetailReqVO()
                .setProcessDefinitionId(template.getId())
                .setProcessVariables(variables)
                .setActivityId(StrUtil.blankToDefault(request.getActivityId(), "StartUserNode"));
        BpmApprovalDetailRespVO detail = processInstanceService.getApprovalDetail(getLoginUserId(), detailReq);
        List<BpmApprovalDetailRespVO.ActivityNode> nodes = resolvePreviewNodes(detailReq, detail);
        return genericPreviewPayload(template, detail, nodes);
    }

    /** Create a durable generic approval draft; no BPM process is started. */
    @PostMapping("/approvals/generic/draft")
    @Operation(summary = "生成任意可发起审批模板草稿")
    @SuppressWarnings("unchecked")
    public Map<String, Object> createGenericApprovalDraft(@Valid @RequestBody GenericApprovalPreviewRequest request) {
        BpmProcessDefinitionRespVO template = resolveVisibleTemplate(request.getProcessDefinition());
        Map<String, Object> variables = validateGenericVariables(template, request.getVariables(), request.getActivityId());
        Map<String, Object> preview = previewGenericApproval(request);
        String runId = requiredBinding(request.getRunId());
        String threadId = requiredBinding(request.getThreadId());
        String messageId = requiredBinding(request.getMessageId());
        String operationId = requiredBinding(request.getOperationId());
        String canonical = template.getId() + "|" + JsonUtils.toJsonString(variables) + "|"
                + JsonUtils.toJsonString(request.getStartUserSelectAssignees()) + "|" + runId + "|" + messageId;
        String draftId = "approval-generic:" + UUID.nameUUIDFromBytes(canonical.getBytes(StandardCharsets.UTF_8));
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("operation", "CREATE");
        draft.put("requestType", StrUtil.blankToDefault(template.getKey(), template.getId()));
        draft.put("processDefinition", template.getId());
        draft.put("processDefinitionKey", template.getKey());
        draft.put("processDefinitionName", template.getName());
        draft.put("variables", variables);
        draft.put("startUserSelectAssignees", request.getStartUserSelectAssignees());
        draft.put("preview", preview);
        draft.put("runId", runId); draft.put("threadId", threadId); draft.put("messageId", messageId);
        draft.put("taskId", request.getTaskId());
        draft.put("operationId", operationId);
        String approvalId = agentApprovalService.createGeneric(getTenantId(), getLoginUserId(), runId, threadId,
                messageId, request.getTaskId(), draftId, "APPROVAL_REQUEST_GENERIC", draft, operationId);
        Map<String, Object> approval = agentApprovalService.get(getTenantId(), getLoginUserId(), approvalId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "DRAFT_READY"); result.put("draftId", draftId); result.put("approvalId", approvalId);
        result.put("operationId", operationId);
        result.put("confirmationToken", approvalId); result.put("expiresAt", approval.get("expiresAt"));
        result.put("draft", draft); result.put("preview", preview);
        return result;
    }

    /** Commit a generic template after the official ApprovalCard has approved it. */
    @PostMapping("/approvals/generic/commit")
    @Operation(summary = "提交已确认的通用审批模板草稿")
    @Transactional(rollbackFor = Exception.class)
    @SuppressWarnings("unchecked")
    public Map<String, Object> commitGenericApproval(@RequestBody Map<String, Object> request) {
        String approvalId = requiredBinding(request, "approvalId");
        String idempotencyKey = requiredBinding(request, "idempotencyKey");
        String operationId = requiredBinding(request, "operationId");
        Map<String, Object> binding = agentApprovalService.claimGenericExecution(getTenantId(), getLoginUserId(),
                approvalId, idempotencyKey, "APPROVAL_REQUEST_GENERIC", operationId);
        if (Boolean.TRUE.equals(binding.get("replay"))) {
            Object replay = ((Map<?, ?>) binding.getOrDefault("draft", Collections.emptyMap())).get("result");
            return replay instanceof Map ? new LinkedHashMap<>((Map<String, Object>) replay) : binding;
        }
        Map<String, Object> draft = binding.get("draft") instanceof Map
                ? (Map<String, Object>) binding.get("draft") : Collections.emptyMap();
        try {
            BpmProcessInstanceCreateReqVO create = new BpmProcessInstanceCreateReqVO();
            create.setProcessDefinitionId(requiredValue(draft, "processDefinition"));
            create.setVariables(draft.get("variables") instanceof Map
                    ? new LinkedHashMap<>((Map<String, Object>) draft.get("variables")) : new LinkedHashMap<>());
            if (draft.get("startUserSelectAssignees") instanceof Map) {
                create.setStartUserSelectAssignees((Map<String, List<Long>>) draft.get("startUserSelectAssignees"));
            }
            String processInstanceId = processInstanceService.createProcessInstance(getLoginUserId(), create);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true); result.put("message", "审批申请已提交");
            result.put("processInstanceId", processInstanceId);
            result.put("requestType", draft.get("requestType"));
            agentApprovalService.markGenericCompleted(getTenantId(), getLoginUserId(), approvalId, operationId, result);
            return result;
        } catch (RuntimeException ex) {
            agentApprovalService.releaseGenericExecution(getTenantId(), getLoginUserId(), approvalId, operationId);
            throw ex;
        }
    }

    @PostMapping("/approvals/preview")
    @Operation(summary = "预览审批链路")
    public ApprovalPreviewResponse previewApprovalRequest(@Valid @RequestBody ApprovalPreviewRequest request) {
        BpmApprovalDetailReqVO req = new BpmApprovalDetailReqVO();
        req.setProcessDefinitionId(resolveProcessDefinitionId(request.getRequestType()));
        req.setProcessVariables(toKnownProcessVariables(request));
        req.setActivityId(StrUtil.blankToDefault(request.getActivityId(), "StartUserNode"));
        BpmApprovalDetailRespVO detail = processInstanceService.getApprovalDetail(getLoginUserId(), req);
        List<BpmApprovalDetailRespVO.ActivityNode> nodes = resolvePreviewNodes(req, detail);
        ApprovalPreviewResponse response = new ApprovalPreviewResponse(); response.setRequestType(request.getRequestType());
        response.setRequiresApprovalSelection(nodes.stream().anyMatch(node -> CollUtil.isNotEmpty(node.getCandidateUsers())));
        response.setNextNodes(nodes.stream().map(node -> { ApprovalNode n = new ApprovalNode(); n.setId(node.getId()); n.setName(node.getName()); return n; }).collect(Collectors.toList()));
        response.setNormalizedSummary(nodes.isEmpty() ? "未识别到后续审批节点" : nodes.stream().map(BpmApprovalDetailRespVO.ActivityNode::getName).filter(StrUtil::isNotBlank).collect(Collectors.joining(" -> ")));
        response.setFormFields(detail.getFormFieldsPermission() == null
                ? Collections.emptyList() : new ArrayList<>(detail.getFormFieldsPermission().keySet()));
        return response;
    }

    /**
     * Persist a leave/trip request as a durable Agent draft.  The BPM service
     * is deliberately not called here: this endpoint only creates the
     * approval-card binding and previews the real approval chain.
     */
    @PostMapping("/approvals/request-draft")
    @Operation(summary = "生成请假或出差审批草稿")
    public Map<String, Object> createApprovalRequestDraft(@RequestBody Map<String, Object> request) {
        ApprovalRequestData normalized = toApprovalRequestData(request);
        ApprovalPreviewRequest previewRequest = new ApprovalPreviewRequest();
        previewRequest.setRequestType(normalized.getRequestType());
        previewRequest.setStartTime(normalized.getStartTime());
        previewRequest.setEndTime(normalized.getEndTime());
        previewRequest.setType(normalized.getType());
        previewRequest.setReason(normalized.getReason());
        ApprovalPreviewResponse preview = previewApprovalRequest(previewRequest);

        String runId = requiredBinding(request, "runId");
        String threadId = requiredBinding(request, "threadId");
        String messageId = requiredBinding(request, "messageId");
        String operationId = requiredBinding(request, "operationId");
        String canonical = normalized.getRequestType() + "|" + normalized.getStartTime() + "|"
                + normalized.getEndTime() + "|" + normalized.getType() + "|" + normalized.getReason()
                + "|" + runId + "|" + messageId;
        String draftId = "approval-request:" + UUID.nameUUIDFromBytes(canonical.getBytes(StandardCharsets.UTF_8));
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("requestType", normalized.getRequestType());
        // The durable Approval draft is a cross-request JSON contract. Do not
        // store LocalDateTime directly here: the global Jackson configuration
        // serializes it as epoch milliseconds, while the commit boundary reads
        // the user-facing canonical time format.
        draft.put("startTime", formatApprovalTime(normalized.getStartTime()));
        draft.put("endTime", formatApprovalTime(normalized.getEndTime()));
        draft.put("type", normalized.getType());
        draft.put("reason", normalized.getReason());
        draft.put("startUserSelectAssignees", normalized.getStartUserSelectAssignees());
        draft.put("preview", preview);
        draft.put("operation", "CREATE");
        draft.put("operationId", operationId);
        String approvalId = agentApprovalService.createGeneric(getTenantId(), getLoginUserId(), runId, threadId,
                messageId, null, draftId, "APPROVAL_REQUEST", draft, operationId);
        Map<String, Object> approval = agentApprovalService.get(getTenantId(), getLoginUserId(), approvalId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "DRAFT_READY");
        result.put("draftId", draftId);
        result.put("approvalId", approvalId);
        result.put("operationId", operationId);
        result.put("confirmationToken", approvalId);
        result.put("expiresAt", approval.get("expiresAt"));
        result.put("draft", draft);
        result.put("preview", preview);
        return result;
    }

    /** Submit a confirmed request draft exactly once. */
    @PostMapping("/approvals/request-commit")
    @Operation(summary = "提交已确认的请假或出差审批草稿")
    @Transactional(rollbackFor = Exception.class)
    @SuppressWarnings("unchecked")
    public Map<String, Object> commitApprovalRequest(@RequestBody Map<String, Object> request) {
        String approvalId = requiredBinding(request, "approvalId");
        String idempotencyKey = requiredBinding(request, "idempotencyKey");
        String operationId = requiredBinding(request, "operationId");
        Map<String, Object> binding = agentApprovalService.claimGenericExecution(getTenantId(), getLoginUserId(),
                approvalId, idempotencyKey, "APPROVAL_REQUEST", operationId);
        if (Boolean.TRUE.equals(binding.get("replay"))) {
            Object replay = ((Map<?, ?>) binding.getOrDefault("draft", Collections.emptyMap())).get("result");
            return replay instanceof Map ? new LinkedHashMap<>((Map<String, Object>) replay) : binding;
        }
        Map<String, Object> draft = binding.get("draft") instanceof Map
                ? (Map<String, Object>) binding.get("draft") : Collections.emptyMap();
        String type = String.valueOf(draft.getOrDefault("requestType", ""));
        ApprovalRequestData normalized = toApprovalRequestData(draft);
        try {
            Long businessId;
            String processInstanceId;
            if (LEAVE.equals(type)) {
                BpmOALeaveCreateReqVO req = new BpmOALeaveCreateReqVO().setStartTime(normalized.getStartTime())
                        .setEndTime(normalized.getEndTime()).setType(normalized.getType()).setReason(normalized.getReason())
                        .setStartUserSelectAssignees(normalized.getStartUserSelectAssignees());
                businessId = leaveService.createLeave(getLoginUserId(), req);
                BpmOALeaveDO item = leaveService.getLeave(businessId);
                processInstanceId = item == null ? null : item.getProcessInstanceId();
            } else if (TRIP.equals(type)) {
                BpmOATripCreateReqVO req = new BpmOATripCreateReqVO().setStartTime(normalized.getStartTime())
                        .setEndTime(normalized.getEndTime()).setType(normalized.getType()).setReason(normalized.getReason())
                        .setStartUserSelectAssignees(normalized.getStartUserSelectAssignees());
                businessId = tripService.createTrip(getLoginUserId(), req);
                BpmOATripDO item = tripService.getTrip(businessId);
                processInstanceId = item == null ? null : item.getProcessInstanceId();
            } else {
                throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_TYPE_UNSUPPORTED：当前仅支持请假和出差审批");
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true); result.put("message", "审批申请已提交");
            result.put("businessId", businessId); result.put("processInstanceId", processInstanceId);
            agentApprovalService.markGenericCompleted(getTenantId(), getLoginUserId(), approvalId, operationId, result);
            return result;
        } catch (RuntimeException ex) {
            agentApprovalService.releaseGenericExecution(getTenantId(), getLoginUserId(), approvalId, operationId);
            throw ex;
        }
    }

    /** Persist a user-owned running process withdrawal as an ApprovalCard draft. */
    @PostMapping("/approvals/withdraw-draft")
    @Operation(summary = "生成审批流程撤回草稿")
    public Map<String, Object> createApprovalWithdrawDraft(@RequestBody Map<String, Object> request) {
        String processInstanceId = requiredBinding(request, "processInstanceId");
        String reason = requiredBinding(request, "reason");
        String runId = requiredBinding(request, "runId");
        String threadId = requiredBinding(request, "threadId");
        String messageId = requiredBinding(request, "messageId");
        String operationId = requiredBinding(request, "operationId");
        ProcessInstance instance = processInstanceService.getProcessInstance(processInstanceId);
        if (instance == null || !String.valueOf(getLoginUserId()).equals(instance.getStartUserId())) {
            throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_PROCESS_NOT_FOUND：流程不存在、已结束或无权撤回");
        }
        String draftId = "approval-withdraw:" + UUID.nameUUIDFromBytes(
                (processInstanceId + "|" + reason + "|" + runId + "|" + messageId).getBytes(StandardCharsets.UTF_8));
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("operation", "WITHDRAW"); draft.put("processInstanceId", processInstanceId);
        draft.put("reason", reason); draft.put("processDefinitionId", instance.getProcessDefinitionId());
        draft.put("operationId", operationId);
        String approvalId = agentApprovalService.createGeneric(getTenantId(), getLoginUserId(), runId, threadId,
                messageId, processInstanceId, draftId, "APPROVAL_WITHDRAW", draft, operationId);
        Map<String, Object> approval = agentApprovalService.get(getTenantId(), getLoginUserId(), approvalId);
        Map<String, Object> result = new LinkedHashMap<>(); result.put("status", "DRAFT_READY");
        result.put("draftId", draftId); result.put("approvalId", approvalId); result.put("confirmationToken", approvalId);
        result.put("operationId", operationId);
        result.put("expiresAt", approval.get("expiresAt")); result.put("draft", draft);
        return result;
    }

    /** Execute a confirmed withdrawal through the owner-scoped BPM service. */
    @PostMapping("/approvals/withdraw-commit")
    @Operation(summary = "提交已确认的审批流程撤回")
    @Transactional(rollbackFor = Exception.class)
    @SuppressWarnings("unchecked")
    public Map<String, Object> commitApprovalWithdraw(@RequestBody Map<String, Object> request) {
        String approvalId = requiredBinding(request, "approvalId");
        String idempotencyKey = requiredBinding(request, "idempotencyKey");
        String operationId = requiredBinding(request, "operationId");
        Map<String, Object> binding = agentApprovalService.claimGenericExecution(getTenantId(), getLoginUserId(),
                approvalId, idempotencyKey, "APPROVAL_WITHDRAW", operationId);
        if (Boolean.TRUE.equals(binding.get("replay"))) {
            Object replay = ((Map<?, ?>) binding.getOrDefault("draft", Collections.emptyMap())).get("result");
            return replay instanceof Map ? new LinkedHashMap<>((Map<String, Object>) replay) : binding;
        }
        Map<String, Object> draft = binding.get("draft") instanceof Map
                ? (Map<String, Object>) binding.get("draft") : Collections.emptyMap();
        String processInstanceId = String.valueOf(draft.getOrDefault("processInstanceId", ""));
        String reason = String.valueOf(draft.getOrDefault("reason", "Agent 撤回")).trim();
        try {
            BpmProcessInstanceCancelReqVO cancel = new BpmProcessInstanceCancelReqVO();
            cancel.setId(processInstanceId); cancel.setReason(reason);
            processInstanceService.cancelProcessInstanceByStartUser(getLoginUserId(), cancel);
            Map<String, Object> result = new LinkedHashMap<>(); result.put("success", true);
            result.put("message", "审批流程已撤回"); result.put("processInstanceId", processInstanceId);
            agentApprovalService.markGenericCompleted(getTenantId(), getLoginUserId(), approvalId, operationId, result);
            return result;
        } catch (RuntimeException ex) {
            agentApprovalService.releaseGenericExecution(getTenantId(), getLoginUserId(), approvalId, operationId);
            throw ex;
        }
    }

    @GetMapping("/approvals/inbox")
    @Operation(summary = "按结构化条件筛选当前用户待办审批")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public ApprovalInboxSearchResponse searchMyApprovalInbox(@Valid ApprovalInboxSearchRequest request) {
        validateInboxSearch(request);
        Long userId = getLoginUserId();
        BpmTaskPageReqVO todoRequest = new BpmTaskPageReqVO();
        todoRequest.setPageNo(1);
        todoRequest.setPageSize(APPROVAL_INBOX_SCAN_LIMIT);
        PageResult<Task> page = taskService.getTaskTodoPage(userId, todoRequest);

        ApprovalInboxSearchResponse response = new ApprovalInboxSearchResponse();
        response.setCriteria(request);
        response.setTotalPending(page.getTotal());
        response.setScannedCount(page.getList().size());
        response.setTruncated(page.getTotal() > page.getList().size());
        response.setCandidates(new ArrayList<>());
        response.setExclusions(new ArrayList<>());
        response.setSortApplied(request.getSortBy());
        response.setNullPolicy(isAmountSort(request.getSortBy()) ? "EXCLUDE" : "N/A");
        response.setSortableCount(0);
        response.setExcludedNullCount(0);
        response.setReturnedCount(0);
        if (CollUtil.isEmpty(page.getList())) {
            response.setMatchedCount(0);
            response.setExcludedCount(0);
            return response;
        }

        Map<String, ProcessInstance> instances = processInstanceService.getProcessInstanceMap(
                convertSet(page.getList(), Task::getProcessInstanceId));
        Set<Long> startUserIds = instances.values().stream()
                .map(this::parseStartUserId).filter(Objects::nonNull).collect(Collectors.toCollection(LinkedHashSet::new));
        Map<Long, AdminUserRespDTO> users = startUserIds.isEmpty()
                ? Collections.emptyMap() : adminUserApi.getUserMap(startUserIds);
        Set<Long> deptIds = users.values().stream().map(AdminUserRespDTO::getDeptId)
                .filter(Objects::nonNull).collect(Collectors.toCollection(LinkedHashSet::new));
        Map<Long, DeptRespDTO> departments = deptIds.isEmpty() ? Collections.emptyMap() : deptApi.getDeptMap(deptIds);
        Map<String, ProcessDefinition> definitions = processDefinitionService.getProcessDefinitionMap(
                convertSet(page.getList(), Task::getProcessDefinitionId));

        AgentApprovalInboxFilter.Criteria criteria = new AgentApprovalInboxFilter.Criteria(
                request.getProcessTypes(), request.getAmountOperator(), request.getAmount(), request.getCreatedFrom(),
                request.getCreatedTo(), request.getDepartment(), request.getMinPendingDays(), request.getAmountPresent());
        LocalDateTime now = LocalDateTime.now();
        int excludedCount = 0;
        for (Task task : page.getList()) {
            ApprovalInboxItem item = toApprovalInboxItem(task, instances.get(task.getProcessInstanceId()),
                    definitions.get(task.getProcessDefinitionId()), users, departments, now);
            List<String> reasons = AgentApprovalInboxFilter.exclusionReasons(criteria,
                    new AgentApprovalInboxFilter.Candidate(item.getProcessDefinitionName(), item.getProcessDefinitionKey(),
                            item.getAmount(), item.getCreatedTime(), item.getDepartmentName()), now);
            if (reasons.isEmpty()) {
                response.getCandidates().add(item);
                continue;
            }
            excludedCount++;
            item.setExclusionReasons(reasons);
            reasons.forEach(reason -> response.getExclusionReasonCounts().merge(reason, 1, Integer::sum));
            if (response.getExclusions().size() < APPROVAL_INBOX_EXCLUSION_LIMIT) {
                response.getExclusions().add(item);
            }
        }
        if (isAmountSort(request.getSortBy())) {
            // Amount ordering has a semantic null policy: records without a
            // known amount cannot participate in an amount ranking. Keep the
            // exclusion visible and deterministic instead of letting nulls
            // occupy the requested top-N slots.
            List<ApprovalInboxItem> amountCandidates = new ArrayList<>();
            for (ApprovalInboxItem item : response.getCandidates()) {
                if (item.getAmount() != null) {
                    amountCandidates.add(item);
                    continue;
                }
                excludedCount++;
                response.setExcludedNullCount(response.getExcludedNullCount() + 1);
                item.setExclusionReasons(Collections.singletonList("AMOUNT_UNAVAILABLE"));
                response.getExclusionReasonCounts().merge("AMOUNT_UNAVAILABLE", 1, Integer::sum);
                if (response.getExclusions().size() < APPROVAL_INBOX_EXCLUSION_LIMIT) {
                    response.getExclusions().add(item);
                }
            }
            response.setCandidates(amountCandidates);
        }
        sortInboxItems(response.getCandidates(), request.getSortBy());
        response.setMatchedCount(response.getCandidates().size());
        response.setExcludedCount(excludedCount);
        response.setSortableCount((int) response.getCandidates().stream()
                .filter(item -> item.getAmount() != null).count());
        int displayLimit = request.getPageSize() == null ? 20 : request.getPageSize();
        if (response.getCandidates().size() > displayLimit) {
            response.setCandidates(new ArrayList<>(response.getCandidates().subList(0, displayLimit)));
        }
        response.setReturnedCount(response.getCandidates().size());
        return response;
    }

    @GetMapping("/approvals/insights")
    @Operation(summary = "分析当前用户待办审批异常和汇总")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public ApprovalInsightResponse approvalInsights(@Valid ApprovalInboxSearchRequest request) {
        ApprovalInboxSearchResponse inbox = searchMyApprovalInbox(request);
        ApprovalInsightResponse response = new ApprovalInsightResponse();
        response.setScannedCount(inbox.getScannedCount());
        Map<String, ApprovalInsightGroup> groups = new LinkedHashMap<>();
        for (ApprovalInboxItem item : inbox.getCandidates()) {
            String groupKey = StrUtil.blankToDefault(item.getDepartmentName(), "未分配部门");
            ApprovalInsightGroup group = groups.get(groupKey);
            if (group == null) {
                group = new ApprovalInsightGroup(); group.setKey(groupKey); group.setCount(0);
                group.setTotalAmount(BigDecimal.ZERO); group.setMaxPendingDays(0); groups.put(groupKey, group);
            }
            group.setCount(group.getCount() + 1);
            if (item.getAmount() != null) group.setTotalAmount(group.getTotalAmount().add(item.getAmount()));
            group.setMaxPendingDays(Math.max(group.getMaxPendingDays(), item.getPendingDays() == null ? 0 : item.getPendingDays()));
            List<String> reasons = new ArrayList<>();
            if (item.getPendingDays() != null && item.getPendingDays() >= 3) reasons.add("PENDING_OVER_3_DAYS");
            if (item.getAmount() != null && item.getAmount().compareTo(new BigDecimal("10000")) >= 0) reasons.add("HIGH_AMOUNT");
            if (!reasons.isEmpty()) {
                ApprovalInsightItem anomaly = new ApprovalInsightItem();
                anomaly.setTaskId(item.getTaskId()); anomaly.setProcessName(item.getProcessDefinitionName());
                anomaly.setStartUserName(item.getStartUserName()); anomaly.setDepartmentName(item.getDepartmentName());
                anomaly.setAmount(item.getAmount()); anomaly.setCreatedTime(item.getCreatedTime() == null ? null : item.getCreatedTime().toString());
                anomaly.setReasons(reasons); response.getAnomalies().add(anomaly);
            }
        }
        response.setGroups(new ArrayList<>(groups.values()));
        response.setSummary("已分析 " + inbox.getCandidates().size() + " 条待办，发现 " + response.getAnomalies().size() + " 条需要关注的审批");
        return response;
    }

    @GetMapping("/approvals/applications")
    @Operation(summary = "查询当前用户发起的审批流程")
    @PreAuthorize("@ss.hasPermission('bpm:process-instance:query')")
    public Map<String, Object> listMyApprovalApplications(@Valid BpmProcessInstancePageReqVO request) {
        normalizePage(request);
        PageResult<HistoricProcessInstance> page = processInstanceService.getProcessInstancePage(
                getLoginUserId(), request);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", page.getTotal());
        result.put("pageNo", request.getPageNo());
        result.put("pageSize", request.getPageSize());
        result.put("items", page.getList().stream().map(this::toApplicationItem).collect(Collectors.toList()));
        result.put("readOnly", true);
        return result;
    }

    @GetMapping("/approvals/applications/{processInstanceId}")
    @Operation(summary = "读取当前用户发起的审批流程详情")
    @PreAuthorize("@ss.hasPermission('bpm:process-instance:query')")
    public Map<String, Object> getMyApprovalApplication(@PathVariable String processInstanceId) {
        HistoricProcessInstance instance = processInstanceService.getHistoricProcessInstance(processInstanceId);
        if (instance == null || !String.valueOf(getLoginUserId()).equals(instance.getStartUserId())) {
            throw ServiceExceptionUtil.exception0(404, "审批流程不存在、已结束或无权访问");
        }
        Map<String, Object> result = toApplicationItem(instance);
        result.put("tasks", taskService.getTaskListByProcessInstanceId(processInstanceId, true).stream()
                .map(this::toHistoryTaskItem).collect(Collectors.toList()));
        return result;
    }

    @GetMapping("/approvals/history")
    @Operation(summary = "查询当前用户已办审批历史")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public Map<String, Object> listMyApprovalHistory(@Valid BpmTaskPageReqVO request) {
        normalizePage(request);
        PageResult<HistoricTaskInstance> page = taskService.getTaskDonePage(getLoginUserId(), request);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("total", page.getTotal());
        result.put("pageNo", request.getPageNo());
        result.put("pageSize", request.getPageSize());
        result.put("items", page.getList().stream().map(this::toHistoryTaskItem).collect(Collectors.toList()));
        result.put("readOnly", true);
        return result;
    }

    @GetMapping("/approvals/report")
    @Operation(summary = "汇总当前用户待办审批报表")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public Map<String, Object> approvalReport(@Valid ApprovalInboxSearchRequest request) {
        ApprovalInboxSearchResponse inbox = searchMyApprovalInbox(request);
        Map<String, Integer> byProcess = new LinkedHashMap<>();
        Map<String, Integer> byDepartment = new LinkedHashMap<>();
        BigDecimal totalAmount = BigDecimal.ZERO;
        int amountCount = 0;
        for (ApprovalInboxItem item : inbox.getCandidates()) {
            byProcess.merge(StrUtil.blankToDefault(item.getProcessDefinitionName(), "未命名流程"), 1, Integer::sum);
            byDepartment.merge(StrUtil.blankToDefault(item.getDepartmentName(), "未分配部门"), 1, Integer::sum);
            if (item.getAmount() != null) {
                totalAmount = totalAmount.add(item.getAmount());
                amountCount++;
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportType", "approval");
        result.put("total", inbox.getMatchedCount());
        result.put("scannedCount", inbox.getScannedCount());
        result.put("excludedCount", inbox.getExcludedCount());
        result.put("totalAmount", totalAmount);
        result.put("amountCount", amountCount);
        result.put("byProcess", byProcess);
        result.put("byDepartment", byDepartment);
        result.put("items", inbox.getCandidates());
        result.put("readOnly", true);
        return result;
    }

    private void normalizePage(BpmProcessInstancePageReqVO request) {
        request.setPageNo(Math.max(1, Math.min(request.getPageNo(), 10000)));
        request.setPageSize(Math.max(1, Math.min(request.getPageSize(), 50)));
    }

    private void normalizePage(BpmTaskPageReqVO request) {
        request.setPageNo(Math.max(1, Math.min(request.getPageNo(), 10000)));
        request.setPageSize(Math.max(1, Math.min(request.getPageSize(), 50)));
    }

    private Map<String, Object> toApplicationItem(HistoricProcessInstance instance) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("processInstanceId", instance.getId());
        item.put("name", instance.getName());
        item.put("processDefinitionId", instance.getProcessDefinitionId());
        item.put("businessKey", instance.getBusinessKey());
        item.put("startUserId", instance.getStartUserId());
        item.put("startTime", instance.getStartTime());
        item.put("endTime", instance.getEndTime());
        item.put("durationInMillis", instance.getDurationInMillis());
        item.put("status", cn.iocoder.yudao.module.bpm.framework.flowable.core.util.FlowableUtils.getProcessInstanceStatus(instance));
        item.put("formVariables", instance.getProcessVariables() == null ? Collections.emptyMap() : instance.getProcessVariables());
        return item;
    }

    private Map<String, Object> toHistoryTaskItem(HistoricTaskInstance task) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("taskId", task.getId());
        item.put("name", task.getName());
        item.put("processInstanceId", task.getProcessInstanceId());
        item.put("processDefinitionId", task.getProcessDefinitionId());
        item.put("taskDefinitionKey", task.getTaskDefinitionKey());
        item.put("assignee", task.getAssignee());
        item.put("owner", task.getOwner());
        item.put("createTime", task.getCreateTime());
        item.put("endTime", task.getEndTime());
        item.put("durationInMillis", task.getDurationInMillis());
        item.put("deleteReason", task.getDeleteReason());
        item.put("description", task.getDescription());
        return item;
    }

    @PostMapping("/approvals/batch/preview")
    @Operation(summary = "预览批量审批操作，不执行写入")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    public ApprovalBatchPreviewResponse previewApprovalBatch(@Valid @RequestBody ApprovalBatchPreviewRequest request) {
        String action = validateBatchPreview(request);
        Long userId = getLoginUserId();
        List<ApprovalInboxItem> selected = request.getTaskIds() == null || request.getTaskIds().isEmpty()
                ? selectBatchByCriteria(userId, request.getCriteria())
                : selectBatchByTaskIds(userId, request.getTaskIds());
        if (selected.isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_EMPTY：没有满足条件的当前待办");
        }
        if (selected.size() > 20) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_TOO_LARGE：一次最多确认 20 条待办");
        }
        List<Map<String, Object>> safeTasks = selected.stream().map(this::toBatchSafeData).collect(Collectors.toList());
        AgentApprovalBatchPreviewService.StoredPreview saved = approvalBatchPreviewService.create(
                getTenantId(), userId, action, normalizeBatchReason(action, request.getReason()), request.getPreviewMessageId(),
                request.getRunId(), request.getThreadId(), request.getOperationId(), safeTasks);
        ApprovalBatchPreviewResponse response = new ApprovalBatchPreviewResponse();
        response.setPreviewId(saved.getPreviewId());
        response.setOperationId(saved.getOperationId());
        response.setConfirmationToken(saved.getConfirmationToken());
        response.setAction(saved.getAction());
        response.setReason(saved.getReason());
        response.setTaskCount(saved.getTasks().size());
        response.setTasks(selected);
        response.setExpiresAt(saved.getExpiresAt());
        return response;
    }

    @GetMapping("/approvals/batch/{previewId}")
    @Operation(summary = "读取批量审批确认状态")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    public Map<String, Object> getApprovalBatch(@PathVariable String previewId) {
        return approvalBatchPreviewService.get(getTenantId(), getLoginUserId(), previewId);
    }

    /**
     * Re-read BPM facts after a response was lost between the MySQL commit and
     * the Agent PostgreSQL preview update.  The endpoint never accepts a
     * claimed result from Python; the reconciliation service reads Flowable.
     */
    @PostMapping("/approvals/batch/{previewId}/reconcile")
    @Operation(summary = "核对批量审批外部结果")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    public Map<String, Object> reconcileApprovalBatch(@PathVariable String previewId,
                                                      @RequestBody Map<String, Object> request) {
        return approvalBatchReconciliationService.reconcile(
                getTenantId(), getLoginUserId(), requiredBinding(previewId),
                requiredBinding(request, "confirmationToken"),
                requiredBinding(request, "operationId"),
                requiredBinding(request, "idempotencyKey"));
    }

    /**
     * This endpoint records only the user's ApprovalCard decision. The BPM
     * mutation remains exclusively inside executeApprovalBatch after the
     * corresponding official LangGraph HITL resume.
     */
    @PostMapping("/approvals/batch/{previewId}/{decision}")
    @Operation(summary = "确认或取消批量审批卡片")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    public Map<String, Object> decideApprovalBatch(@PathVariable String previewId, @PathVariable String decision,
                                                    @RequestBody Map<String, Object> request) {
        String normalized = decision == null ? "" : decision.trim().toUpperCase();
        String key = request.get("idempotencyKey") == null ? null : String.valueOf(request.get("idempotencyKey"));
        String reason = request.get("reason") == null ? null : String.valueOf(request.get("reason"));
        return approvalBatchPreviewService.decide(getTenantId(), getLoginUserId(), previewId, normalized, key, reason);
    }

    /**
     * The BPM part of this endpoint uses the primary (MySQL) transaction. We
     * re-check every task immediately before mutation, then either all tasks
     * advance or the BPM transaction rolls back as one unit.
     */
    @PostMapping("/approvals/batch/execute")
    @Operation(summary = "确认后原子执行批量审批")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    @Transactional(transactionManager = "transactionManager", rollbackFor = Exception.class)
    public ApprovalBatchExecuteResponse executeApprovalBatch(@Valid @RequestBody ApprovalBatchExecuteRequest request) {
        Long tenantId = getTenantId();
        Long userId = getLoginUserId();
        AgentApprovalBatchPreviewService.BatchClaim claim = approvalBatchPreviewService.claim(
                tenantId, userId, request.getPreviewId(), request.getConfirmationToken(),
                request.getOperationId(), request.getIdempotencyKey(), request.getConfirmationMessageId());
        if (claim.isReplay()) {
            ApprovalBatchExecuteResponse replay = claim.getReplayResponse();
            replay.setIdempotentReplay(true);
            return replay;
        }
        try {
            Map<String, Object> preview = claim.getPreview();
            String action = String.valueOf(preview.get("action"));
            String reason = String.valueOf(preview.get("reason"));
            List<String> taskIds = batchTaskIds(preview);
            // Validate the full set before the first mutation. A stale task,
            // ownership change, or a process-specific required field aborts
            // this MySQL transaction instead of producing a partial batch.
            for (String taskId : taskIds) {
                if (taskService.getTodoTask(userId, taskId, null) == null) {
                    throw ServiceExceptionUtil.exception0(409,
                            "AGENT_APPROVAL_BATCH_STALE：待办已处理、无权访问或状态改变，请重新筛选");
                }
                taskService.validateTask(userId, taskId);
            }
            for (int index = 0; index < taskIds.size(); index++) {
                String taskId = taskIds.get(index);
                if ("APPROVE".equals(action)) {
                    taskService.approveTask(userId, new BpmTaskApproveReqVO().setId(taskId).setReason(reason));
                } else {
                    taskService.rejectTask(userId, new BpmTaskRejectReqVO().setId(taskId).setReason(reason));
                }
                if (index == 0) {
                    approvalBatchTestHook.afterFirstMutation();
                }
            }
            ApprovalBatchExecuteResponse response = new ApprovalBatchExecuteResponse();
            response.setPreviewId(request.getPreviewId()); response.setAction(action); response.setSuccess(true);
            response.setIdempotentReplay(false);
            response.setResults(taskIds.stream().map(taskId -> {
                ApprovalBatchItemResult item = new ApprovalBatchItemResult();
                item.setTaskId(taskId); item.setStatus("SUCCESS");
                item.setMessage("APPROVE".equals(action) ? "审批通过" : "审批驳回"); return item;
                }).collect(Collectors.toList()));
            // The preview is stored in Agent PostgreSQL, while the BPM
            // mutation commits in the primary MySQL transaction. Marking the
            // preview complete before that commit would create a false
            // success if the primary transaction fails at commit time.
            if (!TransactionSynchronizationManager.isSynchronizationActive()) {
                throw new IllegalStateException("批量审批缺少主事务提交同步上下文");
            }
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    approvalBatchPreviewService.complete(tenantId, userId, request.getPreviewId(),
                            request.getIdempotencyKey(), response);
                }

                @Override
                public void afterCompletion(int status) {
                    if (status != STATUS_COMMITTED) {
                        approvalBatchPreviewService.release(tenantId, userId, request.getPreviewId(),
                                request.getIdempotencyKey());
                    }
                }
            });
            return response;
        } catch (RuntimeException ex) {
            // No write is committed when BPM throws: the primary transaction
            // rolls back. Release the independent confirmation claim so the
            // user can re-preview or retry after correcting the real cause.
            approvalBatchPreviewService.release(tenantId, userId, request.getPreviewId(), request.getIdempotencyKey());
            throw ex;
        }
    }

    @GetMapping("/tasks/todo")
    @Operation(summary = "获取我的待办任务")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public TodoTaskPageResponse listMyTodoTasks(@RequestParam(defaultValue = "1") Integer pageNo, @RequestParam(defaultValue = "10") Integer pageSize) {
        BpmTaskPageReqVO req = new BpmTaskPageReqVO(); req.setPageNo(pageNo); req.setPageSize(pageSize); PageResult<Task> page = taskService.getTaskTodoPage(getLoginUserId(), req);
        TodoTaskPageResponse response = new TodoTaskPageResponse(); response.setPageNo(pageNo); response.setPageSize(pageSize); response.setTotal(page.getTotal());
        if (CollUtil.isEmpty(page.getList())) { response.setList(Collections.emptyList()); return response; }
        Map<String, ProcessInstance> instances = processInstanceService.getProcessInstanceMap(convertSet(page.getList(), Task::getProcessInstanceId));
        Map<Long, AdminUserRespDTO> users = adminUserApi.getUserMap(convertSet(instances.values(), i -> Long.valueOf(i.getStartUserId())));
        Map<String, BpmProcessDefinitionInfoDO> definitions = processDefinitionService.getProcessDefinitionInfoMap(convertSet(page.getList(), Task::getProcessDefinitionId));
        PageResult<BpmTaskRespVO> tasks = BpmTaskConvert.INSTANCE.buildTodoTaskPage(page, instances, users, definitions);
        response.setList(tasks.getList().stream().map(task -> { TodoTask item = new TodoTask(); item.setTaskId(task.getId()); item.setName(task.getName()); item.setProcessInstanceId(task.getProcessInstanceId()); item.setCreatedTime(task.getCreateTime()); if (task.getProcessInstance() != null) { item.setProcessDefinitionName(task.getProcessInstance().getName()); if (task.getProcessInstance().getStartUser() != null) { item.setStartUserId(task.getProcessInstance().getStartUser().getId()); item.setStartUserName(task.getProcessInstance().getStartUser().getNickname()); }} if (task.getAssigneeUser() != null) { item.setAssigneeUserId(task.getAssigneeUser().getId()); item.setAssigneeUserName(task.getAssigneeUser().getNickname()); } return item; }).collect(Collectors.toList())); return response;
    }

    @GetMapping("/tasks/{taskId}")
    @Operation(summary = "获取我当前待办的审批详情")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public TodoTaskDetail getMyTodoTask(@PathVariable String taskId) {
        BpmTaskRespVO task = taskService.getTodoTask(getLoginUserId(), taskId, null);
        if (task == null) {
            throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_TASK_NOT_FOUND：待办不存在、已处理或无权访问");
        }
        TodoTaskDetail response = new TodoTaskDetail();
        response.setTaskId(task.getId()); response.setName(task.getName()); response.setProcessInstanceId(task.getProcessInstanceId());
        response.setReason(task.getReason()); response.setReasonRequire(task.getReasonRequire());
        response.setFormFields(task.getFormFields() == null ? Collections.emptyList() : task.getFormFields());
        response.setFormVariables(task.getFormVariables() == null ? Collections.emptyMap() : task.getFormVariables());
        if (task.getProcessInstance() != null) {
            response.setProcessDefinitionName(task.getProcessInstance().getName());
            if (task.getProcessInstance().getStartUser() != null) response.setStartUserName(task.getProcessInstance().getStartUser().getNickname());
        }
        return response;
    }

    @PostMapping("/tasks/action-preview")
    @Operation(summary = "生成单条待办审批操作预览")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    public Map<String, Object> previewTodoTaskAction(@RequestBody Map<String, Object> request) {
        String taskId = request.get("taskId") == null ? "" : String.valueOf(request.get("taskId")).trim();
        String action = request.get("action") == null ? "" : String.valueOf(request.get("action")).trim().toUpperCase(Locale.ROOT);
        String reason = request.get("reason") == null ? "" : String.valueOf(request.get("reason")).trim();
        String operationId = request.get("operationId") == null ? "" : String.valueOf(request.get("operationId")).trim();
        String runId = request.get("runId") == null ? "" : String.valueOf(request.get("runId")).trim();
        String threadId = request.get("threadId") == null ? "" : String.valueOf(request.get("threadId")).trim();
        String messageId = request.get("messageId") == null ? "" : String.valueOf(request.get("messageId")).trim();
        if (taskId.isEmpty() || operationId.isEmpty()
                || (!"APPROVE".equals(action) && !"REJECT".equals(action))
                || ("REJECT".equals(action) && reason.isEmpty()) || reason.length() > 500) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_ACTION_PREVIEW_INVALID：任务、动作和驳回理由不完整");
        }
        operationId = requiredBinding(operationId);
        BpmTaskRespVO task = taskService.getTodoTask(getLoginUserId(), taskId, null);
        if (task == null) throw ServiceExceptionUtil.exception0(404, "AGENT_APPROVAL_TASK_NOT_FOUND：待办不存在、已处理或无权访问");
        String draftId = "approval-task:" + UUID.nameUUIDFromBytes((taskId + "|" + action + "|" + reason + "|" + runId + "|" + messageId).getBytes(StandardCharsets.UTF_8));
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("taskId", taskId); draft.put("action", action); draft.put("reason", reason);
        draft.put("operationId", operationId);
        draft.put("name", task.getName()); draft.put("processInstanceId", task.getProcessInstanceId());
        draft.put("processDefinitionName", task.getProcessInstance() == null ? null : task.getProcessInstance().getName());
        draft.put("reasonRequired", task.getReasonRequire());
        String approvalId = agentApprovalService.createGeneric(getTenantId(), getLoginUserId(), runId, threadId,
                messageId, taskId, draftId, "APPROVAL_TASK", draft, operationId);
        Map<String, Object> approval = agentApprovalService.get(getTenantId(), getLoginUserId(), approvalId);
        if (!operationId.equals(String.valueOf(approval.get("operationId")))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_OPERATION_MISMATCH：预览结果与 Operation 不一致");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("approvalId", approvalId); result.put("operationId", operationId);
        result.put("draftId", draftId); result.put("confirmationToken", approvalId);
        result.put("status", approval.get("status")); result.put("expiresAt", approval.get("expiresAt"));
        result.put("draft", draft); result.put("task", getMyTodoTask(taskId));
        return result;
    }

    @PostMapping("/tasks/action-execute")
    @Operation(summary = "执行已确认的单条待办审批")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> executeTodoTaskAction(@RequestBody Map<String, Object> request) {
        String approvalId = request.get("approvalId") == null ? "" : String.valueOf(request.get("approvalId")).trim();
        String key = request.get("idempotencyKey") == null ? "" : String.valueOf(request.get("idempotencyKey")).trim();
        String operationId = request.get("operationId") == null ? "" : String.valueOf(request.get("operationId")).trim();
        if (approvalId.isEmpty() || key.isEmpty() || operationId.isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_EXECUTION_INVALID：审批标识、Operation 和幂等键不能为空");
        }
        operationId = requiredBinding(operationId);
        Map<String, Object> binding = agentApprovalService.claimGenericExecution(getTenantId(), getLoginUserId(), approvalId, key,
                "APPROVAL_TASK", operationId);
        if (Boolean.TRUE.equals(binding.get("replay"))) {
            Object replay = binding.get("draft") instanceof Map ? ((Map<?, ?>) binding.get("draft")).get("result") : null;
            return replay instanceof Map ? new LinkedHashMap<>((Map<String, Object>) replay) : binding;
        }
        Map<String, Object> draft = binding.get("draft") instanceof Map ? (Map<String, Object>) binding.get("draft") : Collections.emptyMap();
        String taskId = String.valueOf(draft.getOrDefault("taskId", ""));
        String action = String.valueOf(draft.getOrDefault("action", ""));
        String reason = String.valueOf(draft.getOrDefault("reason", ""));
        try {
            taskService.validateTask(getLoginUserId(), taskId);
            if ("APPROVE".equals(action)) {
                taskService.approveTask(getLoginUserId(), new BpmTaskApproveReqVO().setId(taskId).setReason(reason));
            } else if ("REJECT".equals(action)) {
                taskService.rejectTask(getLoginUserId(), new BpmTaskRejectReqVO().setId(taskId).setReason(reason));
            } else {
                throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_ACTION_INVALID：不支持的审批动作");
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true); result.put("taskId", taskId); result.put("action", action);
            result.put("message", "APPROVE".equals(action) ? "审批通过" : "审批驳回");
            agentApprovalService.markGenericCompleted(getTenantId(), getLoginUserId(), approvalId, operationId, result);
            return result;
        } catch (RuntimeException ex) {
            agentApprovalService.releaseGenericExecution(getTenantId(), getLoginUserId(), approvalId, operationId);
            throw ex;
        }
    }

    @GetMapping("/tasks/action-status")
    @Operation(summary = "查询单条待办审批动作的最终结果")
    @PreAuthorize("@ss.hasPermission('bpm:task:query')")
    public Map<String, Object> getTodoTaskActionStatus(@RequestParam String approvalId,
                                                       @RequestParam String operationId) {
        String validApprovalId = requiredBinding(approvalId);
        String validOperationId = requiredBinding(operationId);
        Map<String, Object> approval = agentApprovalService.get(getTenantId(), getLoginUserId(), validApprovalId);
        if (!"APPROVAL_TASK".equals(approval.get("draftType"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_CONTEXT_INVALID：该审批不是单条待办审批操作");
        }
        String approvalOperationId = optionalString(approval.get("operationId"));
        if (!validOperationId.equals(approvalOperationId)) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_OPERATION_MISMATCH：审批与当前 Operation 不一致");
        }
        Map<String, Object> draft = approval.get("draft") instanceof Map
                ? (Map<String, Object>) approval.get("draft") : Collections.emptyMap();
        String taskId = optionalString(draft.get("taskId"));
        if (taskId.isEmpty()) taskId = optionalString(approval.get("taskId"));
        String action = optionalString(draft.get("action")).toUpperCase(Locale.ROOT);
        if (taskId.isEmpty() || (!"APPROVE".equals(action) && !"REJECT".equals(action))) {
            throw ServiceExceptionUtil.exception0(409,
                    "AGENT_APPROVAL_CONTEXT_INVALID：单条审批快照缺少任务或动作");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("approvalId", validApprovalId);
        result.put("operationId", validOperationId);
        result.put("taskId", taskId);
        result.put("action", action);
        if ("COMPLETED".equals(approval.get("status")) && draft.get("result") instanceof Map) {
            // The Java Approval row already contains the committed result.
            // Return it directly instead of reinterpreting current BPM state.
            result.put("status", "SUBMITTED");
            result.put("result", new LinkedHashMap<>((Map<String, Object>) draft.get("result")));
            return result;
        }
        Task activeTask = taskService.getTask(taskId);
        if (activeTask != null) {
            result.put("status", "PENDING");
            return result;
        }
        HistoricTaskInstance historicTask = taskService.getHistoricTask(taskId);
        if (historicTask == null) {
            result.put("status", "UNKNOWN");
            return result;
        }
        if (historicTask.getEndTime() == null) {
            result.put("status", "UNKNOWN");
            return result;
        }
        Object rawTaskStatus = historicTask.getTaskLocalVariables() == null ? null
                : historicTask.getTaskLocalVariables().get(BpmnVariableConstants.TASK_VARIABLE_STATUS);
        Integer taskStatus = rawTaskStatus instanceof Number ? ((Number) rawTaskStatus).intValue() : null;
        boolean matched = ("APPROVE".equals(action)
                && (BpmTaskStatusEnum.APPROVE.getStatus().equals(taskStatus)
                || BpmTaskStatusEnum.APPROVING.getStatus().equals(taskStatus)))
                || ("REJECT".equals(action) && BpmTaskStatusEnum.REJECT.getStatus().equals(taskStatus));
        result.put("taskStatus", taskStatus);
        result.put("status", matched ? "SUBMITTED" : "FAILED_FINAL");
        Map<String, Object> actionResult = new LinkedHashMap<>();
        actionResult.put("success", matched);
        actionResult.put("taskId", taskId);
        actionResult.put("action", action);
        actionResult.put("message", matched ? ("APPROVE".equals(action) ? "审批通过" : "审批驳回") : "待办状态与原审批动作不一致");
        result.put("result", actionResult);
        return result;
    }

    @PostMapping("/tasks/action-reconcile")
    @Operation(summary = "核对并完成单条待办审批动作")
    @PreAuthorize("@ss.hasPermission('bpm:task:update')")
    @SuppressWarnings("unchecked")
    public Map<String, Object> reconcileTodoTaskAction(@RequestBody Map<String, Object> request) {
        String approvalId = requiredBinding(request, "approvalId");
        String operationId = requiredBinding(request, "operationId");
        // This method is deliberately the only write-capable reconciliation
        // path. The status resolver still owns the Flowable read and the
        // service below only accepts the resulting operation-bound proof.
        Map<String, Object> status = getTodoTaskActionStatus(approvalId, operationId);
        if ("SUBMITTED".equals(status.get("status"))) {
            Map<String, Object> actionResult = status.get("result") instanceof Map
                    ? new LinkedHashMap<>((Map<String, Object>) status.get("result"))
                    : new LinkedHashMap<>();
            Map<String, Object> approval = agentApprovalService.completeGenericExecution(
                    getTenantId(), getLoginUserId(), approvalId, "APPROVAL_TASK", operationId, actionResult);
            status.put("approvalStatus", approval.get("status"));
        }
        return status;
    }

    private String validateBatchPreview(ApprovalBatchPreviewRequest request) {
        boolean hasIds = !CollUtil.isEmpty(request.getTaskIds());
        boolean hasCriteria = request.getCriteria() != null;
        if (hasIds == hasCriteria) {
            throw ServiceExceptionUtil.exception0(400,
                    "AGENT_APPROVAL_BATCH_SELECTION_INVALID：必须且只能提供 taskIds 或 criteria");
        }
        String action = StrUtil.blankToDefault(request.getAction(), "").trim().toUpperCase(Locale.ROOT);
        if (!Arrays.asList("APPROVE", "REJECT").contains(action)) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_ACTION_INVALID：action 仅支持 APPROVE 或 REJECT");
        }
        String reason = normalizeBatchReason(action, request.getReason());
        if ("REJECT".equals(action) && StrUtil.isBlank(reason)) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_REASON_REQUIRED：批量驳回必须填写统一理由");
        }
        if (hasIds) {
            Set<String> normalized = request.getTaskIds().stream().filter(StrUtil::isNotBlank)
                    .map(String::trim).collect(Collectors.toCollection(LinkedHashSet::new));
            if (normalized.size() != request.getTaskIds().size()) {
                throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_SELECTION_INVALID：taskIds 不能为空或重复");
            }
            request.setTaskIds(new ArrayList<>(normalized));
        } else {
            validateInboxSearch(request.getCriteria());
            // A criteria selection must stay intentionally narrow. The server
            // rejects broad/truncated results below rather than silently
            // approving only the first page.
            request.getCriteria().setPageSize(20);
        }
        return action;
    }

    private String normalizeBatchReason(String action, String reason) {
        String normalized = reason == null ? "" : reason.trim();
        if (normalized.length() > 500) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BATCH_REASON_INVALID：审批意见不能超过 500 个字符");
        }
        return "APPROVE".equals(action) && normalized.isEmpty() ? "同意" : normalized;
    }

    private List<ApprovalInboxItem> selectBatchByTaskIds(Long userId, List<String> taskIds) {
        List<ApprovalInboxItem> selected = new ArrayList<>();
        for (String taskId : taskIds) {
            // getTodoTask applies the current-user todo visibility rule; the
            // second validation checks current assignee immediately as well.
            BpmTaskRespVO detail = taskService.getTodoTask(userId, taskId, null);
            if (detail == null) {
                throw ServiceExceptionUtil.exception0(404,
                        "AGENT_APPROVAL_BATCH_TASK_NOT_FOUND：待办不存在、已处理或无权访问");
            }
            Task task = taskService.validateTask(userId, taskId);
            ApprovalInboxItem item = new ApprovalInboxItem();
            item.setTaskId(taskId); item.setName(task.getName()); item.setProcessInstanceId(task.getProcessInstanceId());
            if (detail.getProcessInstance() != null) {
                item.setProcessDefinitionName(detail.getProcessInstance().getName());
                if (detail.getProcessInstance().getStartUser() != null) {
                    item.setStartUserName(detail.getProcessInstance().getStartUser().getNickname());
                }
            }
            item.setCreatedTime(task.getCreateTime() == null ? null : DateUtils.of(task.getCreateTime()));
            item.setPendingDays(AgentApprovalInboxFilter.pendingDays(item.getCreatedTime(), LocalDateTime.now()));
            selected.add(item);
        }
        return selected;
    }

    private List<ApprovalInboxItem> selectBatchByCriteria(Long userId, ApprovalInboxSearchRequest criteria) {
        // Reuse the same permission-filtered, deterministic read boundary as
        // P0. A batch preview must never reinterpret natural language locally.
        ApprovalInboxSearchResponse result = searchMyApprovalInbox(criteria);
        if (result.isTruncated()) {
            throw ServiceExceptionUtil.exception0(400,
                    "AGENT_APPROVAL_BATCH_FILTER_TOO_BROAD：筛选范围超过安全扫描上限，请缩小类型、金额或时间条件");
        }
        if (result.getMatchedCount() != null && result.getMatchedCount() > 20) {
            throw ServiceExceptionUtil.exception0(400,
                    "AGENT_APPROVAL_BATCH_TOO_LARGE：筛选结果超过 20 条，请继续缩小条件");
        }
        return result.getCandidates() == null ? Collections.emptyList() : result.getCandidates();
    }

    private Map<String, Object> toBatchSafeData(ApprovalInboxItem item) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("taskId", item.getTaskId());
        result.put("name", item.getName());
        result.put("processInstanceId", item.getProcessInstanceId());
        result.put("processDefinitionName", item.getProcessDefinitionName());
        result.put("processDefinitionKey", item.getProcessDefinitionKey());
        result.put("startUserName", item.getStartUserName());
        result.put("departmentName", item.getDepartmentName());
        result.put("amount", item.getAmount());
        result.put("createdTime", item.getCreatedTime());
        result.put("pendingDays", item.getPendingDays());
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<String> batchTaskIds(Map<String, Object> preview) {
        Object value = preview.get("taskIds");
        if (!(value instanceof List)) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_DATA_INVALID：批量审批预览缺少任务列表");
        }
        List<String> ids = ((List<?>) value).stream().filter(Objects::nonNull).map(String::valueOf)
                .filter(StrUtil::isNotBlank).collect(Collectors.toList());
        if (ids.isEmpty() || ids.size() > 20 || ids.size() != new LinkedHashSet<>(ids).size()) {
            throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_BATCH_DATA_INVALID：批量审批预览任务列表无效");
        }
        return ids;
    }

    private BpmProcessDefinitionRespVO resolveVisibleTemplate(String selector) {
        String normalized = StrUtil.trim(selector);
        if (normalized.isEmpty()) throw ServiceExceptionUtil.exception0(400, "审批模板不能为空");
        return approvalTemplateService.getApprovalTemplateList(getLoginUserId()).stream()
                .filter(item -> normalized.equals(item.getId()) || normalized.equals(item.getKey()))
                .findFirst()
                .orElseThrow(() -> ServiceExceptionUtil.exception0(404, "当前用户没有可发起的审批模板: " + normalized));
    }

    private Map<String, Object> validateGenericVariables(BpmProcessDefinitionRespVO template,
                                                          Map<String, Object> input,
                                                          String activityId) {
        Map<String, Object> variables = input == null ? new LinkedHashMap<>() : new LinkedHashMap<>(input);
        Set<String> forbidden = genericForbiddenFields();
        List<String> declared = resolveGenericFormFields(template, activityId);
        for (String key : variables.keySet()) {
            if (key == null || key.trim().isEmpty() || forbidden.contains(key)
                    || key.startsWith("_")) {
                throw ServiceExceptionUtil.exception0(400, "审批表单字段无效: " + key);
            }
            if (!declared.isEmpty() && declared.stream().noneMatch(raw -> declaredFieldMatches(raw, key))) {
                throw ServiceExceptionUtil.exception0(400, "字段不属于审批模板表单: " + key);
            }
        }
        if (declared.isEmpty() && !variables.isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "审批模板没有声明可写入的表单字段: " + variables.keySet());
        }
        return variables;
    }

    /**
     * The template list is only a metadata projection.  Normal BPMN forms
     * often leave its formFields array empty, while the deployed start node
     * still declares the actual field permissions.  Resolve that model-level
     * schema before validating variables; never fall back to accepting
     * arbitrary Flowable variables.
     */
    private List<String> resolveGenericFormFields(BpmProcessDefinitionRespVO template, String activityId) {
        LinkedHashSet<String> declared = new LinkedHashSet<>();
        if (template.getFormFields() != null) {
            template.getFormFields().stream()
                    .filter(Objects::nonNull)
                    .map(this::normalizeDeclaredField)
                    .filter(StrUtil::isNotBlank)
                    .forEach(declared::add);
        }
        if (!declared.isEmpty()) {
            return new ArrayList<>(declared);
        }
        BpmnModel bpmnModel = processDefinitionService.getProcessDefinitionBpmnModel(template.getId());
        if (bpmnModel != null) {
            Set<String> visited = new HashSet<>();
            bpmnModel.getProcesses().forEach(process -> collectBpmnFormFields(
                    bpmnModel, process.getFlowElements(), declared, visited));
        }
        return new ArrayList<>(declared);
    }

    /** Template metadata may contain either a plain field name or a JSON form-field descriptor. */
    @SuppressWarnings("unchecked")
    private String normalizeDeclaredField(String raw) {
        String value = raw.trim();
        if (!value.startsWith("{")) {
            return value;
        }
        try {
            Map<String, Object> descriptor = JsonUtils.parseObject(value, Map.class);
            Object field = descriptor.get("field");
            if (field == null) field = descriptor.get("name");
            return field == null ? value : String.valueOf(field).trim();
        } catch (RuntimeException ignored) {
            return value;
        }
    }

    private void collectBpmnFormFields(BpmnModel bpmnModel, Collection<FlowElement> elements,
                                       Set<String> declared, Set<String> visited) {
        if (elements == null) {
            return;
        }
        for (FlowElement element : elements) {
            if (element == null || !visited.add(element.getId())) {
                continue;
            }
            Map<String, String> permissions = BpmnModelUtils.parseFormFieldsPermission(bpmnModel, element.getId());
            if (permissions != null) {
                permissions.keySet().stream()
                        .filter(StrUtil::isNotBlank)
                        .filter(key -> !genericForbiddenFields().contains(key) && !key.startsWith("_"))
                        .forEach(declared::add);
            }
            if (element instanceof SubProcess) {
                collectBpmnFormFields(bpmnModel, ((SubProcess) element).getFlowElements(), declared, visited);
            }
        }
    }

    /**
     * Resolve the initial chain without asking the task API for a task that
     * does not exist yet.  Existing task/instance previews retain the richer
     * next-node calculation; pre-start previews use the model-simulated
     * activity nodes returned by getApprovalDetail.
     */
    private List<BpmApprovalDetailRespVO.ActivityNode> resolvePreviewNodes(
            BpmApprovalDetailReqVO request, BpmApprovalDetailRespVO detail) {
        if (StrUtil.isNotBlank(request.getTaskId()) || StrUtil.isNotBlank(request.getProcessInstanceId())) {
            return Optional.ofNullable(processInstanceService.getNextApprovalNodes(getLoginUserId(), request))
                    .orElseGet(Collections::emptyList);
        }
        if (detail == null || detail.getActivityNodes() == null) {
            return Collections.emptyList();
        }
        return detail.getActivityNodes().stream()
                .filter(Objects::nonNull)
                .filter(node -> Objects.equals(BpmSimpleModelNodeTypeEnum.APPROVE_NODE.getType(), node.getNodeType())
                        || Objects.equals(BpmSimpleModelNodeTypeEnum.TRANSACTOR_NODE.getType(), node.getNodeType()))
                .collect(Collectors.toList());
    }

    private Set<String> genericForbiddenFields() {
        return Set.of("startUserId", "status", "skipExpressionEnabled", "processInstanceId",
                "processDefinitionId", "tenantId", "businessKey");
    }

    private boolean declaredFieldMatches(String raw, String key) {
        if (raw == null) return false;
        String value = raw.trim();
        return key.equals(value)
                || value.contains("\"field\":\"" + key + "\"")
                || value.contains("\"name\":\"" + key + "\"");
    }

    private Map<String, Object> genericPreviewPayload(BpmProcessDefinitionRespVO template,
                                                       BpmApprovalDetailRespVO detail,
                                                       List<BpmApprovalDetailRespVO.ActivityNode> nodes) {
        List<Map<String, Object>> nextNodes = nodes.stream().map(node -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", node.getId()); item.put("name", node.getName());
            item.put("candidateUserIds", node.getCandidateUsers());
            return item;
        }).collect(Collectors.toList());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("requestType", StrUtil.blankToDefault(template.getKey(), template.getId()));
        result.put("processDefinitionId", template.getId());
        result.put("processDefinitionName", template.getName());
        List<String> formFields = resolveGenericFormFields(template, null);
        if (formFields.isEmpty() && detail.getFormFieldsPermission() != null) {
            formFields.addAll(detail.getFormFieldsPermission().keySet());
        }
        result.put("formFields", formFields);
        result.put("formFieldPermissions", detail.getFormFieldsPermission() == null
                ? Collections.emptyMap() : detail.getFormFieldsPermission());
        result.put("requiresApprovalSelection", nodes.stream().anyMatch(node -> CollUtil.isNotEmpty(node.getCandidateUsers())));
        result.put("nextNodes", nextNodes);
        result.put("normalizedSummary", nodes.isEmpty() ? "未识别到后续审批节点"
                : nodes.stream().map(BpmApprovalDetailRespVO.ActivityNode::getName).filter(StrUtil::isNotBlank).collect(Collectors.joining(" -> ")));
        return result;
    }

    private String requiredBinding(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BINDING_INVALID：运行上下文不能为空");
        }
        return value.trim();
    }

    private String optionalString(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private String requiredValue(Map<String, Object> source, String key) {
        Object value = source == null ? null : source.get(key);
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "审批草稿缺少字段: " + key);
        }
        return String.valueOf(value).trim();
    }

    private String resolveRequestType(String key) { if (LEAVE_KEY.equals(key)) return LEAVE; if (TRIP_KEY.equals(key)) return TRIP; return key; }
    private String resolveProcessDefinitionId(String type) { if (LEAVE.equals(type)) return findDefinitionId(LEAVE_KEY); if (TRIP.equals(type)) return findDefinitionId(TRIP_KEY); throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_TYPE_UNSUPPORTED：当前仅支持请假和出差审批"); }
    private String findDefinitionId(String key) { return approvalTemplateService.getApprovalTemplateList(getLoginUserId()).stream().filter(i -> Objects.equals(i.getKey(), key)).map(BpmProcessDefinitionRespVO::getId).findFirst().orElseThrow(() -> ServiceExceptionUtil.exception0(404, "未找到可用流程定义: " + key)); }

    private String requiredBinding(Map<String, Object> request, String key) {
        Object value = request == null ? null : request.get(key);
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_BINDING_INVALID：" + key + " 不能为空");
        }
        return String.valueOf(value).trim();
    }

    @SuppressWarnings("unchecked")
    private ApprovalRequestData toApprovalRequestData(Map<String, Object> request) {
        if (request == null) throw ServiceExceptionUtil.exception0(400, "审批申请参数不能为空");
        ApprovalRequestData result = new ApprovalRequestData();
        result.setRequestType(requiredBinding(request, "requestType").toLowerCase(Locale.ROOT));
        result.setStartTime(parseApprovalTime(request.get("startTime"), "startTime"));
        result.setEndTime(parseApprovalTime(request.get("endTime"), "endTime"));
        Object type = request.get("type");
        if (type == null) throw ServiceExceptionUtil.exception0(400, "审批类型不能为空");
        try { result.setType(Integer.valueOf(String.valueOf(type))); }
        catch (NumberFormatException ex) { throw ServiceExceptionUtil.exception0(400, "审批类型必须是数字"); }
        result.setReason(requiredBinding(request, "reason"));
        Object assignees = request.get("startUserSelectAssignees");
        if (assignees instanceof Map) {
            Map<String, List<Long>> normalized = new LinkedHashMap<>();
            ((Map<?, ?>) assignees).forEach((key, value) -> {
                if (!(key == null || value == null)) {
                    List<Long> ids = new ArrayList<>();
                    if (value instanceof Collection) {
                        for (Object item : (Collection<?>) value) {
                            try { ids.add(Long.valueOf(String.valueOf(item))); }
                            catch (NumberFormatException ignored) { }
                        }
                    }
                    if (!ids.isEmpty()) normalized.put(String.valueOf(key), ids);
                }
            });
            result.setStartUserSelectAssignees(normalized);
        }
        if (!result.getStartTime().isBefore(result.getEndTime())) {
            throw ServiceExceptionUtil.exception0(400, "审批开始时间必须早于结束时间");
        }
        return result;
    }

    private LocalDateTime parseApprovalTime(Object value, String field) {
        if (value == null || String.valueOf(value).trim().isEmpty()) {
            throw ServiceExceptionUtil.exception0(400, field + " 不能为空");
        }
        if (value instanceof Number) {
            try {
                return LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(((Number) value).longValue()),
                        java.time.ZoneId.systemDefault());
            } catch (RuntimeException ex) {
                throw ServiceExceptionUtil.exception0(400, field + " 时间戳无效");
            }
        }
        String text = String.valueOf(value).trim().replace('T', ' ');
        try { return LocalDateTime.parse(text, DateTimeFormatter.ofPattern(DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)); }
        catch (RuntimeException ex) { throw ServiceExceptionUtil.exception0(400, field + " 时间格式必须为 yyyy-MM-dd HH:mm:ss"); }
    }

    private String formatApprovalTime(LocalDateTime value) {
        return value == null ? null : value.format(
                DateTimeFormatter.ofPattern(DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND));
    }

    private Map<String, Object> toKnownProcessVariables(ApprovalPreviewRequest request) {
        // 与 BpmOALeaveCreateReqVO/BpmOATripCreateReqVO 的固定字段保持一致。
        Map<String, Object> variables = new LinkedHashMap<>();
        variables.put("startTime", request.getStartTime()); variables.put("endTime", request.getEndTime());
        variables.put("type", request.getType()); variables.put("reason", request.getReason());
        return variables;
    }

    private void validateInboxSearch(ApprovalInboxSearchRequest request) {
        boolean hasOperator = StrUtil.isNotBlank(request.getAmountOperator());
        boolean hasAmount = request.getAmount() != null;
        if (hasOperator != hasAmount) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_FILTER_INVALID：金额比较必须同时提供 amountOperator 和 amount");
        }
        if (hasOperator) {
            String operator = request.getAmountOperator().trim().toUpperCase(Locale.ROOT);
            if (!Arrays.asList("LT", "LTE", "EQ", "GTE", "GT").contains(operator)) {
                throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_FILTER_INVALID：amountOperator 仅支持 LT、LTE、EQ、GTE、GT");
            }
            request.setAmountOperator(operator);
        }
        if (request.getCreatedFrom() != null && request.getCreatedTo() != null
                && request.getCreatedFrom().isAfter(request.getCreatedTo())) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_FILTER_INVALID：createdFrom 不能晚于 createdTo");
        }
        String sort = StrUtil.blankToDefault(request.getSortBy(), "CREATED_DESC").trim().toUpperCase(Locale.ROOT);
        if (!Arrays.asList("CREATED_DESC", "CREATED_ASC", "AMOUNT_DESC", "AMOUNT_ASC", "PENDING_DAYS_DESC").contains(sort)) {
            throw ServiceExceptionUtil.exception0(400, "AGENT_APPROVAL_FILTER_INVALID：不支持的待办排序方式");
        }
        request.setSortBy(sort);
    }

    private ApprovalInboxItem toApprovalInboxItem(Task task, ProcessInstance instance, ProcessDefinition definition,
                                                   Map<Long, AdminUserRespDTO> users, Map<Long, DeptRespDTO> departments,
                                                   LocalDateTime now) {
        ApprovalInboxItem item = new ApprovalInboxItem();
        item.setTaskId(task.getId());
        item.setName(task.getName());
        item.setProcessInstanceId(task.getProcessInstanceId());
        item.setProcessDefinitionName(instance != null ? instance.getName() : definition == null ? null : definition.getName());
        item.setProcessDefinitionKey(definition == null ? null : definition.getKey());
        Long startUserId = instance == null ? null : parseStartUserId(instance);
        AdminUserRespDTO startUser = startUserId == null ? null : users.get(startUserId);
        item.setStartUserName(startUser == null ? null : startUser.getNickname());
        DeptRespDTO department = startUser == null || startUser.getDeptId() == null ? null : departments.get(startUser.getDeptId());
        item.setDepartmentName(department == null ? null : department.getName());
        item.setAmount(extractKnownAmount(task.getProcessVariables()));
        LocalDateTime createdTime = task.getCreateTime() == null ? null : DateUtils.of(task.getCreateTime());
        item.setCreatedTime(createdTime);
        item.setPendingDays(AgentApprovalInboxFilter.pendingDays(createdTime, now));
        return item;
    }

    /** Only explicit, business-defined amount keys are eligible for amount filtering. */
    private BigDecimal extractKnownAmount(Map<String, Object> variables) {
        if (variables == null || variables.isEmpty()) {
            return null;
        }
        for (String key : Arrays.asList("amount", "totalAmount", "reimburseAmount", "expenseAmount", "contractAmount")) {
            BigDecimal value = toBigDecimal(variables.get(key));
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private BigDecimal toBigDecimal(Object value) {
        if (value == null) return null;
        if (value instanceof BigDecimal) return (BigDecimal) value;
        if (value instanceof Number || value instanceof String) {
            try {
                return new BigDecimal(String.valueOf(value).trim());
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private Long parseStartUserId(ProcessInstance instance) {
        if (instance == null || StrUtil.isBlank(instance.getStartUserId())) return null;
        try {
            return Long.valueOf(instance.getStartUserId());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private void sortInboxItems(List<ApprovalInboxItem> items, String sortBy) {
        Comparator<ApprovalInboxItem> comparator;
        switch (sortBy) {
            case "CREATED_ASC":
                comparator = Comparator.comparing(ApprovalInboxItem::getCreatedTime, Comparator.nullsLast(Comparator.naturalOrder()));
                break;
            case "AMOUNT_DESC":
                comparator = (left, right) -> compareNullable(right.getAmount(), left.getAmount());
                break;
            case "AMOUNT_ASC":
                comparator = (left, right) -> compareNullable(left.getAmount(), right.getAmount());
                break;
            case "PENDING_DAYS_DESC":
                comparator = Comparator.comparing(ApprovalInboxItem::getPendingDays, Comparator.nullsLast(Comparator.reverseOrder()));
                break;
            case "CREATED_DESC":
            default:
                comparator = (left, right) -> compareNullable(right.getCreatedTime(), left.getCreatedTime());
                break;
        }
        items.sort(comparator.thenComparing(ApprovalInboxItem::getTaskId, Comparator.nullsLast(Comparator.naturalOrder())));
    }

    private boolean isAmountSort(String sortBy) {
        return "AMOUNT_DESC".equals(sortBy) || "AMOUNT_ASC".equals(sortBy);
    }

    private <T extends Comparable<? super T>> int compareNullable(T left, T right) {
        if (left == null && right == null) return 0;
        if (left == null) return 1;
        if (right == null) return -1;
        return left.compareTo(right);
    }
}
