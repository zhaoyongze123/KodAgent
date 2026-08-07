package cn.iocoder.yudao.server.controller.agent.vo;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.Max;
import javax.validation.constraints.Min;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

public class OaAgentFacadeVo {

    private OaAgentFacadeVo() {
    }

    @Data
    @Schema(description = "Agent 审批模板")
    public static class ApprovalType {

        @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
        private String requestType;

        @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
        private String processDefinitionId;

        @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
        private String processDefinitionName;

        private String category;

        private String description;

        /** 当前模板允许提交的表单字段；仅返回字段名，不返回引擎内部变量。 */
        private List<String> formFields;
    }

    @Data
    public static class ApprovalTypeListResponse {

        @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
        private List<ApprovalType> templates;
    }

    @Data
    public static class ApprovalPreviewRequest {

        /**
         * Agent 只支持已建模的请假、出差字段。不能让模型透传任意流程变量，
         * 否则既绕过表单边界，也会把下一审批人等业务事实交给模型决定。
         */
        @NotBlank
        private String requestType;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;

        @NotNull
        private Integer type;

        @NotBlank
        private String reason;

        private String activityId = "StartUserNode";
    }

    @Data
    public static class GenericApprovalPreviewRequest {
        /** 模板 key 或当前用户可发起模板对应的流程定义 ID。 */
        @NotBlank
        private String processDefinition;

        /** 仅允许模板声明的业务表单字段，禁止注入 Flowable 系统变量。 */
        private Map<String, Object> variables = new LinkedHashMap<>();

        private String activityId = "StartUserNode";

        private Map<String, List<Long>> startUserSelectAssignees;

        /** Agent durable binding; these are not business form variables. */
        private String runId;
        private String threadId;
        private String messageId;
        private String taskId;

        /** Python-owned durable Operation bound to this approval draft. */
        @NotBlank @Size(max = 128)
        private String operationId;
    }

    @Data
    public static class ApprovalNode {

        private String id;

        private String name;
    }

    @Data
    public static class ApprovalPreviewResponse {

        private String requestType;

        private boolean requiresApprovalSelection;

        private List<ApprovalNode> nextNodes;

        private String normalizedSummary;

        /** 当前用户可见的流程预览，不返回引擎内部对象。 */
        private List<String> formFields;
    }

    @Data
    public static class ApprovalRequestData {

        @NotBlank
        private String requestType;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;

        @NotNull
        private Integer type;

        @NotBlank
        private String reason;

        private Map<String, List<Long>> startUserSelectAssignees;
    }

    @Data
    public static class TodoTaskPageResponse {

        private Integer pageNo;

        private Integer pageSize;

        private Long total;

        private List<TodoTask> list;
    }

    @Data
    public static class TodoTask {

        private String taskId;

        private String name;

        private String processInstanceId;

        private String processDefinitionName;

        private Long startUserId;

        private String startUserName;

        private Long assigneeUserId;

        private String assigneeUserName;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime createdTime;
    }

    @Data
    public static class TodoTaskDetail {

        private String taskId;

        private String name;

        private String processInstanceId;

        private String processDefinitionName;

        private String startUserName;

        private String reason;

        private Boolean reasonRequire;

        /** 该待办已由 Java 按当前用户权限过滤后的只读表单数据。 */
        private List<String> formFields;

        private Map<String, Object> formVariables;
    }

    /**
     * Structured, read-only Agent criteria. Process type is matched against the
     * BPM definition name/key; the model must never provide a task id to widen
     * its own read scope.
     */
    @Data
    public static class ApprovalInboxSearchRequest {

        private List<String> processTypes;

        /** LT, LTE, EQ, GTE or GT. Must be paired with amount. */
        private String amountOperator;

        private BigDecimal amount;

        /** When true, only records with a usable amount participate in the query. */
        private Boolean amountPresent;

        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime createdFrom;

        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime createdTo;

        private String department;

        /** Minimum full days the task has remained pending since its creation. */
        @Min(0)
        @Max(3650)
        private Integer minPendingDays;

        /** CREATED_DESC, CREATED_ASC, AMOUNT_DESC, AMOUNT_ASC or PENDING_DAYS_DESC. */
        private String sortBy = "CREATED_DESC";

        /** Maximum number of matching candidates to display; scanning is server bounded. */
        @Min(1)
        @Max(50)
        private Integer pageSize = 20;
    }

    @Data
    public static class ApprovalInboxItem {

        private String taskId;

        private String name;

        private String processInstanceId;

        private String processDefinitionName;

        private String processDefinitionKey;

        private String startUserName;

        private String departmentName;

        private BigDecimal amount;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime createdTime;

        private Integer pendingDays;

        /** Present only on an excluded item; the client must show, not hide, these facts. */
        private List<String> exclusionReasons;
    }

    @Data
    public static class ApprovalInboxSearchResponse {

        private ApprovalInboxSearchRequest criteria;

        /** Number of current-user BPM pending tasks before the Agent conditions are applied. */
        private Long totalPending;

        /** Number actually scanned under the server safety limit. */
        private Integer scannedCount;

        /** Matching items before the response display limit is applied. */
        private Integer matchedCount;

        private List<ApprovalInboxItem> candidates;

        private Integer excludedCount;

        /** First excluded items with deterministic reason codes for auditability. */
        private List<ApprovalInboxItem> exclusions;

        private Map<String, Integer> exclusionReasonCounts = new LinkedHashMap<>();

        /** Number of returned candidates that contain a usable amount. */
        private Integer sortableCount;

        /** Number of candidates excluded because amount sorting cannot use null values. */
        private Integer excludedNullCount;

        /** Number of candidates after filtering and response page limit. */
        private Integer returnedCount;

        /** The server-applied stable sort, copied from the validated request. */
        private String sortApplied;

        /** Null handling policy used for amount sorting. */
        private String nullPolicy;

        /** True means more current-user pending items existed than the bounded scan inspected. */
        private boolean truncated;
    }

    @Data
    public static class ApprovalInsightResponse {
        private Integer scannedCount;
        private List<ApprovalInsightItem> anomalies = new ArrayList<>();
        private List<ApprovalInsightGroup> groups = new ArrayList<>();
        private String summary;
    }

    @Data
    public static class ApprovalInsightItem {
        private String taskId;
        private String processName;
        private String startUserName;
        private String departmentName;
        private BigDecimal amount;
        private String createdTime;
        private List<String> reasons = new ArrayList<>();
    }

    @Data
    public static class ApprovalInsightGroup {
        private String key;
        private Integer count;
        private BigDecimal totalAmount;
        private Integer maxPendingDays;
    }

    /**
     * A one-time, server-owned preview for a batch BPM action.  The Agent may
     * describe a target set, but it never supplies process variables or a
     * next-assignee map.  A caller must use either explicit task ids or the
     * same bounded inbox criteria used by the read-only search endpoint.
     */
    @Data
    public static class ApprovalBatchPreviewRequest {

        /** APPROVE or REJECT. */
        @NotBlank
        private String action;

        /** Approval comment. Rejection requires a non-blank reason. */
        private String reason;

        @Size(max = 20)
        private List<@NotBlank String> taskIds;

        private ApprovalInboxSearchRequest criteria;

        /** Gateway-issued id of the message that generated this preview. */
        @NotBlank
        @Size(max = 128)
        private String previewMessageId;

        @Size(max = 128)
        private String runId;

        @Size(max = 128)
        private String threadId;

        /** Python-owned durable Operation bound to this preview. */
        @NotBlank
        @Size(max = 128)
        private String operationId;

        @Size(max = 128)
        private String messageId;

        @Size(max = 128)
        private String idempotencyKey;
    }

    @Data
    public static class ApprovalBatchPreviewResponse {

        private String previewId;

        private String operationId;

        /** Opaque, short-lived proof required by the following confirmation turn. */
        private String confirmationToken;

        private String action;

        private String reason;

        private Integer taskCount;

        private List<ApprovalInboxItem> tasks;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime expiresAt;
    }

    @Data
    public static class ApprovalBatchExecuteRequest {

        @NotBlank
        @Size(max = 64)
        private String previewId;

        @NotBlank
        @Size(max = 128)
        private String operationId;

        @NotBlank
        @Size(max = 128)
        private String confirmationToken;

        /** Stable for a preview/token pair; protects network retries. */
        @NotBlank
        @Size(max = 128)
        private String idempotencyKey;

        /** Must be a later user turn than previewMessageId. */
        @NotBlank
        @Size(max = 128)
        private String confirmationMessageId;
    }

    @Data
    public static class ApprovalBatchItemResult {

        private String taskId;

        private String status;

        private String message;
    }

    @Data
    public static class ApprovalBatchExecuteResponse {

        private String previewId;

        private String action;

        private boolean success;

        private boolean idempotentReplay;

        private List<ApprovalBatchItemResult> results;
    }

    @Data
    public static class MeetingRoom {

        private Long id;

        private String name;

        private String location;
    }

    @Data
    public static class MeetingRoomListResponse {

        private List<MeetingRoom> rooms;
    }

    @Data
    public static class MeetingConflictCheckRequest {

        private Long bookingId;

        @NotNull
        private Long meetingRoomId;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;
    }

    @Data
    public static class MeetingConflict {

        private Long bookingId;

        private Long meetingRoomId;

        private String meetingRoomName;

        private Long applicantUserId;

        private String applicantUserNickname;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;
    }

    @Data
    public static class MeetingConflictCheckResponse {

        private boolean hasConflict;

        private List<MeetingConflict> conflicts;
    }

    @Data
    public static class MeetingBookingCreateRequest {

        /** Agent 草稿 ID；正式提交必须绑定一个待确认草稿。 */
        @NotBlank
        private String draftId;

        /** 审批事实 ID；必须与草稿 approval_id 完全一致。 */
        @NotBlank
        private String approvalId;

        /** Python Runtime Operation ID; Java verifies it against the stored draft. */
        @NotBlank
        @Size(max = 128)
        private String operationId;

        private String subject;

        private Long meetingRoomId;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;

        private List<Long> attendeeUserIds;

        private String remark;

        private Boolean forceConflict;

        private String cancelReason;
    }

    @Data
    public static class MeetingBookingCreateResponse {

        private boolean success;

        private Long bookingId;

        private String operation;

        private String message;
    }

    @Data
    public static class MeetingBookingDetailResponse {
        private Long bookingId;
        private String subject;
        private Long meetingRoomId;
        private String meetingRoomName;
        private Long applicantUserId;
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;
        private List<Long> attendeeUserIds;
        private String remark;
        private Integer status;
        /** Only an applicant may alter or cancel this booking. */
        private boolean editable;
    }

    @Data
    public static class MeetingBookingListResponse {
        private List<MeetingBookingDetailResponse> bookings;
    }

    @Data
    public static class CalendarEvent {

        private String sourceType;

        private Long sourceId;

        private String title;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;

        private Boolean editable;

        private String location;

        private String description;

        private Long meetingRoomId;

        private String meetingRoomName;

        private List<Long> attendeeUserIds;

        private List<String> attendeeUserNicknames;

        private String otherParticipants;
    }

    @Data
    public static class MyCalendarResponse {

        private List<CalendarEvent> events;
    }

    @Data
    public static class UserCalendarRequest {

        @NotEmpty
        private List<Long> userIds;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @NotNull
        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;
    }

    @Data
    public static class UserCalendarResponse {

        private Long userId;

        private String userNickname;

        private List<CalendarEvent> events;
    }

    /**
     * Agent-facing draft contract for a mutable personal schedule.  A
     * MEETING_BOOKING never appears here and is deliberately not editable.
     */
    @Data
    public static class PersonalScheduleDraftRequest {

        @NotBlank
        private String operation; // CREATE, UPDATE, CANCEL

        private Long sourceScheduleId;

        private String title;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime startTime;

        @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
        private LocalDateTime endTime;

        private String location;
        private String description;
        private List<Long> attendeeUserIds;
        private String otherParticipants;
        /** Only an explicit user decision may set this on the persisted draft. */
        private Boolean allowConflictOverride = false;

        @NotBlank private String runId;
        @NotBlank private String threadId;
        @NotBlank private String messageId;
        private String taskId;
        /** Python Runtime Operation ID; new writes must preserve this binding. */
        @NotBlank @Size(max = 128) private String operationId;
        @NotBlank private String idempotencyKey;

        public Map<String, Object> toMap() {
            Map<String, Object> value = new java.util.LinkedHashMap<>();
            value.put("operation", operation); value.put("sourceScheduleId", sourceScheduleId);
            value.put("title", title); value.put("startTime", startTime == null ? null : startTime.format(java.time.format.DateTimeFormatter.ofPattern(FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)));
            value.put("endTime", endTime == null ? null : endTime.format(java.time.format.DateTimeFormatter.ofPattern(FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)));
            value.put("location", location); value.put("description", description); value.put("attendeeUserIds", attendeeUserIds);
            value.put("otherParticipants", otherParticipants); value.put("allowConflictOverride", Boolean.TRUE.equals(allowConflictOverride));
            value.put("runId", runId); value.put("threadId", threadId); value.put("messageId", messageId); value.put("taskId", taskId); value.put("idempotencyKey", idempotencyKey);
            value.put("operationId", operationId);
            return value;
        }
    }

    @Data
    public static class PersonalScheduleCommitRequest {
        @NotBlank private String draftId;
        @NotBlank private String approvalId;
        @NotBlank @Size(max = 128) private String operationId;
    }

    @Data
    public static class UserSimple {

        private Long id;

        private String nickname;

        private Long deptId;

        private String deptName;
    }

    @Data
    public static class UserSearchResponse {

        private List<UserSimple> users;
    }
}
