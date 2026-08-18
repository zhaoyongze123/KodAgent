package cn.iocoder.yudao.server.service.agent;

import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Java-owned registry for the Agent business-action contract.
 *
 * <p>The controller is only a transport adapter. Keeping the contract in a
 * service makes it independently testable and gives the Python planner one
 * stable, runtime-owned source of truth for action ids, fields, permissions,
 * and confirmation boundaries. Executor names and Java paths intentionally do
 * not appear in this public contract.</p>
 */
@Service
public class AgentActionCatalogRegistry {

    public static final String CONTRACT_VERSION = "agent-actions-v1";

    private final List<Map<String, Object>> actions;

    public AgentActionCatalogRegistry() {
        List<Map<String, Object>> built = buildActions();
        validateContract(built);
        this.actions = Collections.unmodifiableList(built);
    }

    public String contractVersion() {
        return CONTRACT_VERSION;
    }

    /**
     * Return a defensive snapshot so a serializer or test cannot mutate the
     * registry used by later requests.
     */
    public List<Map<String, Object>> actions() {
        List<Map<String, Object>> snapshot = new ArrayList<>();
        for (Map<String, Object> action : actions) {
            Map<String, Object> copy = new LinkedHashMap<>(action);
            copy.put("fields", copyFields(castList(action.get("fields"))));
            copy.put("requiredFields", new ArrayList<>(castList(action.get("requiredFields"))));
            copy.put("constraints", copyConstraints(castList(action.get("constraints"))));
            snapshot.add(copy);
        }
        return snapshot;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> copyFields(List<?> source) {
        List<Map<String, Object>> fields = new ArrayList<>();
        for (Object value : source) {
            if (value instanceof Map) {
                fields.add(new LinkedHashMap<>((Map<String, Object>) value));
            }
        }
        return fields;
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> copyConstraints(List<?> source) {
        List<Map<String, Object>> constraints = new ArrayList<>();
        for (Object value : source) {
            if (!(value instanceof Map)) {
                continue;
            }
            Map<String, Object> copy = new LinkedHashMap<>((Map<String, Object>) value);
            Object fields = copy.get("fields");
            if (fields instanceof List) {
                copy.put("fields", new ArrayList<>((List<?>) fields));
            }
            Object groups = copy.get("groups");
            if (groups instanceof List) {
                List<Object> groupCopy = new ArrayList<>();
                for (Object group : (List<?>) groups) {
                    groupCopy.add(group instanceof List ? new ArrayList<>((List<?>) group) : group);
                }
                copy.put("groups", groupCopy);
            }
            Object requires = copy.get("requires");
            if (requires instanceof List) {
                copy.put("requires", new ArrayList<>((List<?>) requires));
            }
            constraints.add(copy);
        }
        return constraints;
    }

    @SuppressWarnings("unchecked")
    private static List castList(Object value) {
        return value instanceof List ? (List) value : Collections.emptyList();
    }

    /**
     * Validate the catalog at construction time so the Java source of truth
     * cannot publish an action whose requiredFields disagree with fields.
     * Python performs the same check when it synchronizes the per-run
     * snapshot; failing here gives Java tests/startup a deterministic error
     * instead of a latent routing mismatch.
     */
    @SuppressWarnings("unchecked")
    private static void validateContract(List<Map<String, Object>> values) {
        Set<String> actionIds = new HashSet<>();
        for (Map<String, Object> action : values) {
            String actionId = String.valueOf(action.get("actionId"));
            if (actionId.isBlank() || !actionIds.add(actionId)) {
                throw new IllegalStateException("Agent action catalog contains duplicate/empty actionId: " + actionId);
            }
            List<Map<String, Object>> fields = (List<Map<String, Object>>) (List<?>) castList(action.get("fields"));
            Set<String> fieldNames = new HashSet<>();
            Set<String> derivedRequired = new HashSet<>();
            for (Map<String, Object> field : fields) {
                String name = String.valueOf(field.get("name"));
                if (name.isBlank() || !fieldNames.add(name)) {
                    throw new IllegalStateException("Agent action " + actionId + " contains duplicate/empty field: " + name);
                }
                if (Boolean.TRUE.equals(field.get("required"))) {
                    if (Boolean.TRUE.equals(field.get("nullable"))) {
                        throw new IllegalStateException("Required Agent action field is nullable: " + actionId + "." + name);
                    }
                    derivedRequired.add(name);
                }
            }
            Set<String> declaredRequired = new HashSet<>();
            for (Object required : castList(action.get("requiredFields"))) {
                String name = String.valueOf(required);
                if (!fieldNames.contains(name) || !declaredRequired.add(name)) {
                    throw new IllegalStateException("Agent action " + actionId
                            + " requiredFields contains unknown/duplicate field: " + name);
                }
            }
            if (!derivedRequired.equals(declaredRequired)) {
                throw new IllegalStateException("Agent action " + actionId
                        + " requiredFields does not match fields.required");
            }
            if (!(action.get("constraints") instanceof List)) {
                throw new IllegalStateException("Agent action " + actionId + " constraints must be a list");
            }
        }
    }

    private List<Map<String, Object>> buildActions() {
        List<Map<String, Object>> actions = new ArrayList<>();
        // Approvals
        actions.add(action("approval.read.pending", "approval_read", "查询、筛选和排序当前用户待办审批",
                "metadata_query", "PENDING", true, false, "approval:read",
                fields(field("filters", "array", false, "待办筛选条件", "user_input"),
                        field("sort", "object", false, "排序条件", "user_input"),
                        field("limit", "integer", false, "返回条数", "user_input"))));
        actions.add(action("approval.read.analyze", "approval_read", "分析当前用户待办审批",
                "metadata_query", "ANALYZE", true, false, "approval:read", fields()));
        actions.add(action("approval.process.applications", "approval_process", "查询我发起的审批",
                "approval_query", "APPLICATIONS", true, false, "approval:read", fields()));
        actions.add(action("approval.process.application_detail", "approval_process", "查询某条我发起的审批详情",
                "approval_query", "APPLICATION_DETAIL", true, false, "approval:read",
                fields(field("processInstanceId", "string", true, "流程实例编号", "user_input"))));
        actions.add(action("approval.process.history", "approval_process", "查询已办审批历史",
                "approval_query", "HISTORY", true, false, "approval:read", fields()));
        actions.add(action("approval.process.withdraw", "approval_process", "撤回本人仍在运行中的审批",
                "approval_query", "WITHDRAW", false, true, "approval:write",
                fields(field("processInstanceId", "string", true, "流程实例编号", "user_input"),
                        field("reason", "string", true, "撤回理由", "user_input"))));
        actions.add(action("approval.write.request", "approval_write", "发起审批申请草稿",
                "workflow", "CREATE", false, true, "approval:write",
                fields(field("process_definition", "string", true, "审批流程定义标识", "user_input"),
                        field("variables", "object", false, "审批表单字段", "user_input"),
                        field("start_user_select_assignees", "object", false, "发起人选择的审批人", "user_input"))));
        actions.add(action("approval.write.task", "approval_write", "处理单条待办审批",
                "workflow", "TASK_ACTION", false, true, "approval:write",
                fields(field("taskId", "string", true, "待办任务编号", "authorized_query_fact"),
                        fieldEnum("action", "string", true, "通过或驳回", "user_input", "APPROVE", "REJECT"),
                        field("reason", "string", false, "处理意见", "user_input"))));
        actions.add(action("approval.write.batch", "approval_write", "批量处理待办审批",
                "workflow", "BATCH_ACTION", false, true, "approval:write",
                fields(field("taskIds", "array", true, "待办任务编号列表", "authorized_query_fact"),
                        fieldEnum("action", "string", true, "通过或驳回", "user_input", "APPROVE", "REJECT"),
                        field("reason", "string", false, "统一处理意见", "user_input"))));

        // Meeting rooms
        actions.add(action("meeting.query", "meeting", "查询会议室预约和可用资源",
                "metadata_query", "QUERY", true, false, "meeting:read", fields()));
        actions.add(action("meeting.create", "meeting", "创建会议室预约草稿",
                "workflow", "BOOK", false, true, "meeting:booking:create",
                fields(field("subject", "string", true, "会议主题", "user_input"),
                        field("start_time", "datetime", true, "开始时间", "user_input"),
                        field("end_time", "datetime", true, "结束时间", "user_input"),
                        field("attendees", "array", false, "参会人", "user_input"),
                        field("room_preference", "string", false, "会议室偏好", "user_input"),
                        field("equipment", "array", false, "设备要求", "user_input"),
                        field("room_capacity", "integer", false, "会议室容量要求", "user_input"),
                        field("remark", "string", false, "会议备注", "user_input"))));
        actions.add(action("meeting.update", "meeting", "修改已有会议室预约",
                "workflow", "UPDATE", false, true, "meeting:booking:create",
                fields(field("source_booking_id", "integer", true, "来源预约编号", "authorized_query_fact"),
                        field("start_time", "datetime", false, "新的开始时间", "user_input"),
                        field("end_time", "datetime", false, "新的结束时间", "user_input"),
                        field("subject", "string", false, "新的会议主题", "user_input"),
                        field("attendees", "array", false, "新的参会人", "user_input"),
                        field("room_preference", "string", false, "新的会议室偏好", "user_input"),
                        field("equipment", "array", false, "新的设备要求", "user_input"),
                        field("room_capacity", "integer", false, "新的会议室容量要求", "user_input"),
                        field("remark", "string", false, "新的会议备注", "user_input"))));
        actions.add(action("meeting.cancel", "meeting", "取消已有会议室预约",
                "workflow", "CANCEL", false, true, "meeting:booking:create",
                fields(field("source_booking_id", "integer", true, "来源预约编号", "authorized_query_fact"),
                        field("reason", "string", false, "取消原因", "user_input"))));

        // Personal schedules
        actions.add(action("schedule.query", "schedule", "查询个人日程",
                "metadata_query", "QUERY", true, false, "schedule:read",
                fields(field("date", "date", false, "查询日期", "user_input"),
                        field("start_time", "datetime", false, "开始时间", "user_input"),
                        field("end_time", "datetime", false, "结束时间", "user_input"),
                        field("time_range", "object", false, "结构化时间范围", "user_input"))));
        actions.add(action("schedule.create", "schedule", "创建个人日程草稿",
                "workflow", "CREATE", false, true, "schedule:write",
                fields(field("title", "string", true, "日程标题", "user_input"),
                        field("start_time", "datetime", true, "开始时间", "user_input"),
                        field("end_time", "datetime", true, "结束时间", "user_input"),
                        field("description", "string", false, "日程说明", "user_input"),
                        field("location", "string", false, "地点", "user_input"),
                        field("attendees", "array", false, "参与人", "user_input"),
                        field("other_participants", "string", false, "其他参与人", "user_input"))));
        actions.add(action("schedule.update", "schedule", "修改个人日程",
                "workflow", "UPDATE", false, true, "schedule:write",
                fields(field("source_schedule_id", "integer", true, "来源日程编号", "authorized_query_fact"),
                        field("title", "string", false, "新的日程标题", "user_input"),
                        field("start_time", "datetime", false, "新的开始时间", "user_input"),
                        field("end_time", "datetime", false, "新的结束时间", "user_input"),
                        field("description", "string", false, "新的日程说明", "user_input"),
                        field("location", "string", false, "新的地点", "user_input"),
                        field("attendees", "array", false, "新的参与人", "user_input"),
                        field("other_participants", "string", false, "新的其他参与人", "user_input"))));
        actions.add(action("schedule.cancel", "schedule", "取消个人日程",
                "workflow", "CANCEL", false, true, "schedule:write",
                fields(field("source_schedule_id", "integer", true, "来源日程编号", "authorized_query_fact"),
                        field("reason", "string", false, "取消原因", "user_input"))));

        // Party files
        actions.add(action("party_file.metadata", "party_file", "按标题、分类、发布时间等查询党务文件",
                "metadata_query", "METADATA_QUERY", true, false, "party-file:read",
                fields(field("filters", "array", false, "元数据筛选条件", "user_input"),
                        field("rank", "object", false, "排序和目标日期", "user_input"),
                        field("limit", "integer", false, "返回条数", "user_input"),
                        field("projection", "array", false, "返回字段", "user_input"))));
        actions.add(action("party_file.content", "party_file", "检索党务文件正文和条款",
                "content_search", "CONTENT_SEARCH", true, false, "party-file:read",
                fields(field("query", "string", true, "正文检索问题或关键词", "user_input"),
                        field("top_k", "integer", false, "召回条数", "user_input"),
                        field("origin", "string", false, "文件来源筛选", "user_input"),
                        field("doc_type", "string", false, "文件类型筛选", "user_input"))));
        actions.add(action("party_file.compare", "party_file", "比较党务文件版本",
                "document_compare", "COMPARE", true, false, "party-file:read",
                fields(field("left_file_id", "integer", true, "左侧版本文件编号", "authorized_query_fact"),
                        field("right_file_id", "integer", true, "右侧版本文件编号", "authorized_query_fact"))));
        actions.add(action("party_file.compliance", "party_file", "按制度校验审批材料",
                "compliance_check", "COMPLIANCE_CHECK", true, false, "approval:read",
                fields(field("task_id", "string", true, "审批待办编号", "authorized_query_fact"),
                        field("file_id", "integer", true, "制度文件编号", "authorized_query_fact"))));
        actions.add(action("party_file.attachments", "party_file", "查询党务文件附件",
                "metadata_query", "ATTACHMENTS", true, false, "party-file:read",
                fields(field("source_party_file_id", "integer", true, "来源文件编号", "authorized_query_fact"))));
        actions.add(action("party_file.create", "party_file", "创建或发布党务文件草稿",
                "workflow", "CREATE", false, true, "party-file:create",
                fields(field("title", "string", true, "文件标题", "user_input"),
                        field("content", "string", true, "文件正文", "user_input"),
                        // The draft tool infers a human-facing category from
                        // the title/document type, then resolves the tenant
                        // category ID through Java. Do not block a valid
                        // notification request before that deterministic
                        // default can run.
                        field("category_name", "string", false, "文件类别名称（可由标题推断）", "user_input"),
                        field("summary", "string", false, "文件摘要", "user_input"),
                        field("publish_time", "datetime", false, "计划发布时间", "user_input"),
                        field("targets", "array", false, "发布对象", "user_input"),
                        field("distribute_to_self", "boolean", false, "抄送本人", "user_input"),
                        field("attachment_file_ids", "array", false, "附件编号", "user_input"))));
        actions.add(action("party_file.update", "party_file", "修改党务文件草稿",
                "workflow", "UPDATE", false, true, "party-file:update",
                fields(field("source_party_file_id", "integer", true, "来源文件编号", "authorized_query_fact"),
                        field("title", "string", false, "新的文件标题", "user_input"),
                        field("content", "string", false, "新的文件正文", "user_input"),
                        field("category_name", "string", false, "新的文件类别", "user_input"),
                        field("summary", "string", false, "新的文件摘要", "user_input"),
                        field("attachment_file_ids", "array", false, "新的附件编号", "user_input"))));
        actions.add(action("party_file.delete", "party_file", "删除或作废党务文件草稿",
                "workflow", "DELETE", false, true, "party-file:delete",
                fields(field("source_party_file_id", "integer", true, "来源文件编号", "authorized_query_fact"),
                        field("reason", "string", false, "删除或作废原因", "user_input"))));

        // KodCloud project 插件领域：第一期严格只读。任何新建、修改任务或文件写入
        // 必须以后续版本接入统一的编译、HITL、执行回执链路，不能在此处偷偷放行。
        actions.add(action("project.list", "project", "查询当前用户可参与的项目",
                "metadata_query", "LIST", true, false, "project:read",
                fields(field("page_no", "integer", false, "页码", "user_input"),
                        field("page_size", "integer", false, "每页条数", "user_input"))));
        actions.add(action("project.snapshot", "project", "查询项目基本信息、成员和进度快照",
                "metadata_query", "SNAPSHOT", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"))));
        actions.add(action("project.tasks", "project", "查询当前用户可见的项目任务",
                "metadata_query", "TASKS", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"))));
        actions.add(action("project.activity", "project", "查询项目和任务近期活动",
                "metadata_query", "ACTIVITY", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"),
                        field("from_time", "datetime", false, "活动起始时间", "user_input"))));
        actions.add(action("project.documents", "project", "查询项目资料目录状态",
                "metadata_query", "DOCUMENTS", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"))));
        actions.add(action("project.investigate", "project", "根据问题自主调查项目进度、任务、动态和资料",
                "fallback_react", "INVESTIGATE", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"),
                        field("user_question", "string", true, "项目调查问题", "user_input"))));
        actions.add(action("project.knowledge.search", "project", "检索项目资料和共享制度知识",
                "content_search", "KNOWLEDGE_SEARCH", true, false, "project:read",
                fields(field("project_id", "string", true, "项目编号", "user_input"),
                        field("query", "string", true, "资料检索问题或关键词", "user_input"),
                        field("top_k", "integer", false, "召回条数", "user_input"),
                        field("include_policy_library", "boolean", false, "是否同时检索制度库", "user_input"))));
        // Reports
        actions.add(action("reporting.approval", "reporting", "生成审批报表",
                "report", "APPROVAL", true, false, "approval:read",
                fields(field("process_types", "array", false, "审批类型", "user_input"),
                        fieldEnum("amount_operator", "string", false, "金额条件", "user_input", "LT", "LTE", "EQ", "GTE", "GT"),
                        field("amount", "number", false, "金额", "user_input"),
                        field("created_from", "date", false, "创建开始日期", "user_input"),
                        field("created_to", "date", false, "创建结束日期", "user_input"),
                        field("department", "string", false, "责任部门", "user_input"),
                        field("min_pending_days", "integer", false, "最少待办天数", "user_input"),
                        fieldEnum("sort_by", "string", false, "排序方式", "user_input",
                                "CREATED_DESC", "CREATED_ASC", "AMOUNT_DESC", "AMOUNT_ASC", "PENDING_DAYS_DESC"))));
        actions.add(action("reporting.meeting", "reporting", "生成会议报表",
                "report", "MEETING", true, false, "meeting:read",
                fields(field("start_time", "datetime", true, "开始时间", "user_input"),
                        field("end_time", "datetime", true, "结束时间", "user_input"))));
        actions.add(action("reporting.schedule", "reporting", "生成日程报表",
                "report", "SCHEDULE", true, false, "schedule:read",
                fields(field("start_time", "datetime", true, "开始时间", "user_input"),
                        field("end_time", "datetime", true, "结束时间", "user_input"))));
        actions.add(action("reporting.party_file", "reporting", "生成党务文件报表",
                "report", "PARTY_FILE", true, false, "party-file:read",
                fields(field("start_time", "datetime", true, "开始时间", "user_input"),
                        field("end_time", "datetime", true, "结束时间", "user_input"))));
        addValidationConstraints(actions);
        return actions;
    }

    /**
     * Cross-field checks are part of the Java-owned action contract rather
     * than being hidden in one Python workflow.  The Python planner only
     * interprets these portable declarations; domain workflows still own
     * permissions, conflicts and persistence state transitions.
     */
    private void addValidationConstraints(List<Map<String, Object>> actions) {
        constraints(actions, "meeting.create", constraint("interval", "start", "start_time", "end", "end_time"));
        constraints(actions, "meeting.update", constraint("interval", "start", "start_time", "end", "end_time"),
                constraint("at_least_one", "fields", Arrays.asList("start_time", "end_time", "subject", "attendees",
                        "room_preference", "equipment", "room_capacity", "remark")));
        constraints(actions, "schedule.create", constraint("interval", "start", "start_time", "end", "end_time"));
        constraints(actions, "schedule.update", constraint("interval", "start", "start_time", "end", "end_time"),
                constraint("at_least_one", "fields", Arrays.asList("title", "start_time", "end_time", "description",
                        "location", "attendees", "other_participants")));
        constraints(actions, "reporting.meeting", constraint("interval", "start", "start_time", "end", "end_time"));
        constraints(actions, "reporting.schedule", constraint("interval", "start", "start_time", "end", "end_time"));
        constraints(actions, "reporting.party_file", constraint("interval", "start", "start_time", "end", "end_time"));
        constraints(actions, "schedule.query",
                constraint("exclusive_groups", "groups", Arrays.asList(
                        Arrays.asList("date"), Arrays.asList("start_time", "end_time"),
                        Arrays.asList("time_range"))));
        constraints(actions, "approval.write.batch",
                constraint("non_empty_unique", "field", "taskIds"));
        constraints(actions, "party_file.create",
                constraint("non_empty_if_present", "field", "targets"),
                constraint("non_empty_if_present", "field", "attachment_file_ids"));
        constraints(actions, "reporting.approval",
                constraint("paired", "fields", Arrays.asList("created_from", "created_to")),
                constraint("requires_if_present", "field", "amount", "requires", Arrays.asList("amount_operator")),
                constraint("requires_if_present", "field", "amount_operator", "requires", Arrays.asList("amount")));
    }

    private void constraints(List<Map<String, Object>> actions, String actionId,
                             Map<String, Object>... values) {
        for (Map<String, Object> action : actions) {
            if (actionId.equals(action.get("actionId"))) {
                action.put("constraints", Arrays.asList(values));
                return;
            }
        }
    }

    private Map<String, Object> constraint(String type, Object... entries) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("type", type);
        if (entries.length % 2 != 0) {
            throw new IllegalArgumentException("Agent action constraint entries must be key/value pairs");
        }
        for (int index = 0; index < entries.length; index += 2) {
            value.put(String.valueOf(entries[index]), entries[index + 1]);
        }
        return value;
    }

    private Map<String, Object> action(String actionId, String capabilityId, String description,
                                       String executionClass, String operation, boolean readOnly,
                                       boolean requiresConfirmation, String permission,
                                       List<Map<String, Object>> fields) {
        Map<String, Object> action = new LinkedHashMap<>();
        action.put("actionId", actionId);
        action.put("capabilityId", capabilityId);
        action.put("description", description);
        action.put("executionClass", executionClass);
        action.put("operation", operation);
        action.put("readOnly", readOnly);
        action.put("requiresConfirmation", requiresConfirmation);
        action.put("permission", permission);
        action.put("fields", fields);
        List<String> required = new ArrayList<>();
        for (Map<String, Object> field : fields) {
            if (Boolean.TRUE.equals(field.get("required"))) {
                required.add(String.valueOf(field.get("name")));
            }
        }
        action.put("requiredFields", required);
        // Every action carries an explicit (possibly empty) constraints list
        // so consumers do not need a second schema branch for unconstrained
        // actions.
        action.put("constraints", new ArrayList<>());
        return action;
    }

    @SafeVarargs
    private final List<Map<String, Object>> fields(Map<String, Object>... values) {
        if (values == null || values.length == 0) {
            return Collections.emptyList();
        }
        return Arrays.asList(values);
    }

    private Map<String, Object> field(String name, String type, boolean required,
                                      String description, String sourcePolicy) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("name", name);
        value.put("type", type);
        value.put("required", required);
        value.put("nullable", !required);
        value.put("description", description);
        value.put("sourcePolicy", sourcePolicy);
        if ("date".equals(type)) {
            value.put("format", "yyyy-MM-dd");
        } else if ("datetime".equals(type)) {
            value.put("format", "yyyy-MM-dd HH:mm:ss");
        }
        return value;
    }

    private Map<String, Object> fieldEnum(String name, String type, boolean required,
                                          String description, String sourcePolicy,
                                          String... values) {
        Map<String, Object> field = field(name, type, required, description, sourcePolicy);
        field.put("enum", Arrays.asList(values));
        return field;
    }
}
