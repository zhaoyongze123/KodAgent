package cn.iocoder.yudao.module.bpm.framework.flowable.core.util;

import cn.hutool.core.map.MapUtil;
import cn.hutool.core.util.ObjectUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.extra.spring.SpringUtil;
import cn.iocoder.yudao.framework.common.core.KeyValue;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.form.BpmFormFieldVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmProcessDefinitionInfoDO;
import cn.iocoder.yudao.module.bpm.enums.definition.BpmModelFormTypeEnum;
import cn.iocoder.yudao.module.bpm.framework.flowable.config.BpmFlowableProperties;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.enums.BpmnVariableConstants;
import lombok.extern.slf4j.Slf4j;
import lombok.SneakyThrows;
import org.flowable.common.engine.api.delegate.Expression;
import org.flowable.common.engine.api.variable.VariableContainer;
import org.flowable.common.engine.impl.el.ExpressionManager;
import org.flowable.common.engine.impl.identity.Authentication;
import org.flowable.common.engine.impl.variable.MapDelegateVariableContainer;
import org.flowable.engine.ManagementService;
import org.flowable.engine.ProcessEngineConfiguration;
import org.flowable.engine.history.HistoricProcessInstance;
import org.flowable.engine.history.HistoricProcessInstanceQuery;
import org.flowable.engine.impl.cfg.ProcessEngineConfigurationImpl;
import org.flowable.engine.impl.util.CommandContextUtil;
import org.flowable.engine.repository.ModelQuery;
import org.flowable.engine.repository.ProcessDefinitionQuery;
import org.flowable.engine.runtime.ProcessInstance;
import org.flowable.task.api.TaskInfo;
import org.flowable.task.api.TaskQuery;
import org.flowable.task.api.history.HistoricTaskInstanceQuery;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.convertList;

/**
 * Flowable 相关的工具方法
 *
 * @author 芋道源码
 */
@Slf4j
public class FlowableUtils {

    // ========== User 相关的工具方法 ==========

    public static void setAuthenticatedUserId(Long userId) {
        Authentication.setAuthenticatedUserId(String.valueOf(userId));
    }

    public static void clearAuthenticatedUserId() {
        Authentication.setAuthenticatedUserId(null);
    }

    public static <V> V executeAuthenticatedUserId(Long userId, Callable<V> callable) {
        setAuthenticatedUserId(userId);
        try {
            return callable.call();
        } catch (Exception e) {
            throw new RuntimeException(e);
        } finally {
            clearAuthenticatedUserId();
        }
    }

    public static String getTenantId() {
        if (isSingleTenantMode()) {
            return getSingleTenantId();
        }
        Long tenantId = TenantContextHolder.getTenantId();
        return tenantId != null ? String.valueOf(tenantId) : ProcessEngineConfiguration.NO_TENANT_ID;
    }

    /**
     * 单租户模式下，Flowable 的租户字段只作为兼容性元数据，不参与查询隔离。
     * 这样既能读取历史上 tenant_id 为空的流程，也能读取当前租户 1 的流程。
     */
    public static boolean isSingleTenantMode() {
        BpmFlowableProperties properties = getBpmFlowableProperties();
        return properties == null || properties.isSingleTenantEnabled();
    }

    public static String getSingleTenantId() {
        BpmFlowableProperties properties = getBpmFlowableProperties();
        if (properties == null || StrUtil.isBlank(properties.getSingleTenantId())) {
            return "1";
        }
        return properties.getSingleTenantId();
    }

    private static Long getSingleTenantIdAsLong() {
        try {
            return Long.valueOf(getSingleTenantId());
        } catch (NumberFormatException ex) {
            log.warn("[getSingleTenantIdAsLong][Flowable 单租户编号非法，回退到 1：{}]", getSingleTenantId());
            return 1L;
        }
    }

    private static BpmFlowableProperties getBpmFlowableProperties() {
        try {
            return SpringUtil.getBean(BpmFlowableProperties.class);
        } catch (Exception ignored) {
            // 单元测试或 Spring 尚未完成初始化时，使用单租户默认值。
            return null;
        }
    }

    public static ModelQuery applyTenantFilter(ModelQuery query) {
        if (!isSingleTenantMode()) {
            query.modelTenantId(getTenantId());
        }
        return query;
    }

    public static ProcessDefinitionQuery applyTenantFilter(ProcessDefinitionQuery query) {
        if (!isSingleTenantMode()) {
            query.processDefinitionTenantId(getTenantId());
        }
        return query;
    }

    public static HistoricProcessInstanceQuery applyTenantFilter(HistoricProcessInstanceQuery query) {
        if (!isSingleTenantMode()) {
            query.processInstanceTenantId(getTenantId());
        }
        return query;
    }

    public static TaskQuery applyTenantFilter(TaskQuery query) {
        if (!isSingleTenantMode()) {
            query.taskTenantId(getTenantId());
        }
        return query;
    }

    public static HistoricTaskInstanceQuery applyTenantFilter(HistoricTaskInstanceQuery query) {
        if (!isSingleTenantMode()) {
            query.taskTenantId(getTenantId());
        }
        return query;
    }

    public static void execute(String tenantIdStr, Runnable runnable) {
        if (isSingleTenantMode()) {
            TenantUtils.execute(getSingleTenantIdAsLong(), runnable);
            return;
        }
        if (ObjectUtil.isEmpty(tenantIdStr)
                || Objects.equals(tenantIdStr, ProcessEngineConfiguration.NO_TENANT_ID)) {
            runnable.run();
        } else {
            Long tenantId = Long.valueOf(tenantIdStr);
            TenantUtils.execute(tenantId, runnable);
        }
    }

    @SneakyThrows
    public static <V> V execute(String tenantIdStr, Callable<V> callable) {
        if (isSingleTenantMode()) {
            return TenantUtils.execute(getSingleTenantIdAsLong(), callable);
        }
        if (ObjectUtil.isEmpty(tenantIdStr)
                || Objects.equals(tenantIdStr, ProcessEngineConfiguration.NO_TENANT_ID)) {
            return callable.call();
        } else {
            Long tenantId = Long.valueOf(tenantIdStr);
            return TenantUtils.execute(tenantId, callable);
        }
    }

    // ========== Execution 相关的工具方法 ==========

    /**
     * 格式化多实例（并签、或签）的 collectionVariable 变量（多实例对应的多审批人列表）
     *
     * @param activityId 活动编号
     * @return collectionVariable 变量
     */
    public static String formatExecutionCollectionVariable(String activityId) {
        return activityId + "_assignees";
    }

    /**
     * 格式化多实例（并签、或签）的 collectionElementVariable 变量（当前实例对应的一个审批人）
     *
     * @param activityId 活动编号
     * @return collectionElementVariable 变量
     */
    public static String formatExecutionCollectionElementVariable(String activityId) {
        return activityId + "_assignee";
    }

    // ========== ProcessInstance 相关的工具方法 ==========

    public static Integer getProcessInstanceStatus(ProcessInstance processInstance) {
        return getProcessInstanceStatus(processInstance.getProcessVariables());
    }

    public static Integer getProcessInstanceStatus(HistoricProcessInstance processInstance) {
        return getProcessInstanceStatus(processInstance.getProcessVariables());
    }

    /**
     * 获得流程实例的状态
     *
     * @param processVariables 流程实例的 variables
     * @return 状态
     */
    private static Integer getProcessInstanceStatus(Map<String, Object> processVariables) {
        return (Integer) processVariables.get(BpmnVariableConstants.PROCESS_INSTANCE_VARIABLE_STATUS);
    }

    /**
     * 获得流程实例的审批原因
     *
     * @param processInstance 流程实例
     * @return 审批原因
     */
    public static String getProcessInstanceReason(HistoricProcessInstance processInstance) {
        return (String) processInstance.getProcessVariables().get(BpmnVariableConstants.PROCESS_INSTANCE_VARIABLE_REASON);
    }

    /**
     * 获得流程实例的表单
     *
     * @param processInstance 流程实例
     * @return 表单
     */
    public static Map<String, Object> getProcessInstanceFormVariable(ProcessInstance processInstance) {
        Map<String, Object> processVariables = new HashMap<>(processInstance.getProcessVariables());
        return filterProcessInstanceFormVariable(processVariables);
    }

    /**
     * 获得流程实例的表单
     *
     * @param processInstance 流程实例
     * @return 表单
     */
    public static Map<String, Object> getProcessInstanceFormVariable(HistoricProcessInstance processInstance) {
        Map<String, Object> processVariables = new HashMap<>(processInstance.getProcessVariables());
        return filterProcessInstanceFormVariable(processVariables);
    }

    /**
     * 过滤流程实例的表单
     *
     * 为什么要过滤？目前使用 processVariables 存储所有流程实例的拓展字段，需要过滤掉一部分的系统字段，从而实现表单的展示
     *
     * @param processVariables 流程实例的 variables
     * @return 过滤后的表单
     */
    public static Map<String, Object> filterProcessInstanceFormVariable(Map<String, Object> processVariables) {
        processVariables.remove(BpmnVariableConstants.PROCESS_INSTANCE_VARIABLE_STATUS);
        return processVariables;
    }

    /**
     * 获得流程实例的发起用户选择的审批人 Map
     *
     * @param processInstance 流程实例
     * @return 发起用户选择的审批人 Map
     */
    public static Map<String, List<Long>> getStartUserSelectAssignees(ProcessInstance processInstance) {
        return processInstance != null ? getStartUserSelectAssignees(processInstance.getProcessVariables()) : null;
    }

    /**
     * 获得流程实例的发起用户选择的审批人 Map
     *
     * @param processVariables 流程变量
     * @return 发起用户选择的审批人 Map
     */
    @SuppressWarnings("unchecked")
    public static Map<String, List<Long>> getStartUserSelectAssignees(Map<String, Object> processVariables) {
        if (processVariables == null) {
            return new HashMap<>();
        }
        return (Map<String, List<Long>>) processVariables.get(
                BpmnVariableConstants.PROCESS_INSTANCE_VARIABLE_START_USER_SELECT_ASSIGNEES);
    }

    /**
     * 获得流程实例的审批用户选择的下一个节点的审批人 Map
     *
     * @param processInstance 流程实例
     * @return 审批用户选择的下一个节点的审批人Map
     */
    public static Map<String, List<Long>> getApproveUserSelectAssignees(ProcessInstance processInstance) {
        return processInstance != null ? getApproveUserSelectAssignees(processInstance.getProcessVariables()) : null;
    }

    /**
     * 获得流程实例的审批用户选择的下一个节点的审批人 Map
     *
     * @param processVariables 流程变量
     * @return 审批用户选择的下一个节点的审批人Map Map
     */
    @SuppressWarnings("unchecked")
    public static Map<String, List<Long>> getApproveUserSelectAssignees(Map<String, Object> processVariables) {
        if (processVariables == null) {
            return new HashMap<>();
        }
        return (Map<String, List<Long>>) processVariables.get(
                BpmnVariableConstants.PROCESS_INSTANCE_VARIABLE_APPROVE_USER_SELECT_ASSIGNEES);
    }

    /**
     * 获得流程实例的摘要
     *
     * 仅有 {@link BpmModelFormTypeEnum#getType()} 表单，才有摘要。
     * 原因是，只有它才有表单项的配置，从而可以根据配置，展示摘要。
     *
     * @param processDefinitionInfo 流程定义
     * @param processVariables      流程实例的 variables
     * @return 摘要
     */
    public static List<KeyValue<String, String>> getSummary(BpmProcessDefinitionInfoDO processDefinitionInfo,
                                                            Map<String, Object> processVariables) {
        // 只有流程表单才会显示摘要！
        if (ObjectUtil.isNull(processDefinitionInfo)
                || !BpmModelFormTypeEnum.NORMAL.getType().equals(processDefinitionInfo.getFormType())) {
            return null;
        }

        // 解析表单配置
        Map<String, BpmFormFieldVO> formFieldsMap = new HashMap<>();
        processDefinitionInfo.getFormFields().forEach(formFieldStr -> {
            try {
                BpmFormFieldVO formField = JsonUtils.parseObject(formFieldStr, BpmFormFieldVO.class);
                parseFormField(formField, formFieldsMap);
            } catch (RuntimeException ex) {
                // 容错跳过非法表单节点，避免待办/我的流程等摘要查询被单个坏节点拖挂
                log.warn("[getSummary][跳过非法表单字段][processDefinitionId({}) field({})]",
                        processDefinitionInfo.getProcessDefinitionId(), formFieldStr, ex);
            }
        });

        // 情况一：当自定义了摘要
        if (ObjectUtil.isNotNull(processDefinitionInfo.getSummarySetting())
                && Boolean.TRUE.equals(processDefinitionInfo.getSummarySetting().getEnable())) {
            return convertList(processDefinitionInfo.getSummarySetting().getSummary(), item -> {
                BpmFormFieldVO formField = formFieldsMap.get(item);
                if (formField != null) {
                    return new KeyValue<String, String>(formField.getTitle(),
                            processVariables.getOrDefault(item, "").toString());
                }
                return null;
            });
        }

        // 情况二：默认摘要展示前三个表单字段
        return formFieldsMap.entrySet().stream()
                .limit(3)
                .map(entry -> new KeyValue<>(entry.getValue().getTitle(),
                        MapUtil.getStr(processVariables, entry.getValue().getField(), "")))
                .collect(Collectors.toList());
    }

    /**
     * 递归解析表单字段
     */
    private static void parseFormField(BpmFormFieldVO formField, Map<String, BpmFormFieldVO> formFieldsMap) {
        if (formField == null) {
            return;
        }
        // 如果存在 children -> 说明是布局组件
        if (formField.getChildren() != null && !formField.getChildren().isEmpty()) {
            for (BpmFormFieldVO child : formField.getChildren()) {
                parseFormField(child, formFieldsMap);
            }
            return;
        }
        // 真实字段才加入 map
        if (StrUtil.isNotBlank(formField.getField())) {
            formFieldsMap.put(formField.getField(), formField);
        }
    }

    // ========== Task 相关的工具方法 ==========

    /**
     * 获得任务的状态
     *
     * @param task 任务
     * @return 状态
     */
    public static Integer getTaskStatus(TaskInfo task) {
        return (Integer) task.getTaskLocalVariables().get(BpmnVariableConstants.TASK_VARIABLE_STATUS);
    }

    /**
     * 获得任务的审批原因
     *
     * @param task 任务
     * @return 审批原因
     */
    public static String getTaskReason(TaskInfo task) {
        return (String) task.getTaskLocalVariables().get(BpmnVariableConstants.TASK_VARIABLE_REASON);
    }

    /**
     * 获得任务的签名图片 URL
     *
     * @param task 任务
     * @return 签名图片 URL
     */
    public static String getTaskSignPicUrl(TaskInfo task) {
        return (String) task.getTaskLocalVariables().get(BpmnVariableConstants.TASK_SIGN_PIC_URL);
    }

    /**
     * 获得任务的表单
     *
     * @param task 任务
     * @return 表单
     */
    public static Map<String, Object> getTaskFormVariable(TaskInfo task) {
        Map<String, Object> formVariables = new HashMap<>(task.getTaskLocalVariables());
        filterTaskFormVariable(formVariables);
        return formVariables;
    }

    /**
     * 过滤任务的表单
     *
     * 为什么要过滤？目前使用 taskLocalVariables 存储所有任务的拓展字段，需要过滤掉一部分的系统字段，从而实现表单的展示
     *
     * @param taskLocalVariables 任务的 taskLocalVariables
     * @return 过滤后的表单
     */
    public static Map<String, Object> filterTaskFormVariable(Map<String, Object> taskLocalVariables) {
        taskLocalVariables.remove(BpmnVariableConstants.TASK_VARIABLE_STATUS);
        taskLocalVariables.remove(BpmnVariableConstants.TASK_VARIABLE_REASON);
        return taskLocalVariables;
    }

    // ========== Expression 相关的工具方法 ==========

    private static Object getExpressionValue(VariableContainer variableContainer, String expressionString,
                                             ProcessEngineConfigurationImpl processEngineConfiguration) {
        assert processEngineConfiguration != null;
        ExpressionManager expressionManager = processEngineConfiguration.getExpressionManager();
        assert expressionManager != null;
        Expression expression = expressionManager.createExpression(expressionString);
        return expression.getValue(variableContainer);
    }

    public static Object getExpressionValue(VariableContainer variableContainer, String expressionString) {
        ProcessEngineConfigurationImpl processEngineConfiguration = CommandContextUtil.getProcessEngineConfiguration();
        if (processEngineConfiguration != null) {
            return getExpressionValue(variableContainer, expressionString, processEngineConfiguration);
        }
        // 如果 ProcessEngineConfigurationImpl 获取不到，则需要通过 ManagementService 来获取
        ManagementService managementService = SpringUtil.getBean(ManagementService.class);
        assert managementService != null;
        return managementService.executeCommand(context ->
                getExpressionValue(variableContainer, expressionString, CommandContextUtil.getProcessEngineConfiguration()));
    }

    public static Object getExpressionValue(Map<String, Object> variable, String expressionString) {
        VariableContainer variableContainer = new MapDelegateVariableContainer(variable, VariableContainer.empty());
        return getExpressionValue(variableContainer, expressionString);
    }
}
