package cn.iocoder.yudao.server.controller.agent;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.process.BpmProcessDefinitionRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.instance.BpmApprovalDetailReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.instance.BpmApprovalDetailRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.instance.BpmProcessInstanceCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.task.BpmTaskPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.task.vo.task.BpmTaskRespVO;
import cn.iocoder.yudao.module.bpm.convert.task.BpmTaskConvert;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmProcessDefinitionInfoDO;
import cn.iocoder.yudao.module.bpm.service.definition.BpmApprovalTemplateService;
import cn.iocoder.yudao.module.bpm.service.definition.BpmProcessDefinitionService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOALeaveService;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOATripService;
import cn.iocoder.yudao.module.bpm.service.task.BpmProcessInstanceService;
import cn.iocoder.yudao.module.bpm.service.task.BpmTaskService;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import cn.iocoder.yudao.module.system.api.user.dto.AdminUserRespDTO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingConflictCheckReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingCancelReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOATripDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingRoomService;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.*;
import cn.iocoder.yudao.server.service.agent.AgentDraftService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.flowable.engine.runtime.ProcessInstance;
import org.flowable.task.api.Task;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.convertSet;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;
import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Tag(name = "Business Agent Facade")
@RestController
@RequestMapping("/agent/tools")
@Validated
public class OaAgentFacadeController {

    private static final String REQUEST_TYPE_LEAVE = "leave";
    private static final String REQUEST_TYPE_TRIP = "trip";
    private static final String REQUEST_TYPE_GENERIC = "generic";
    private static final String PROCESS_KEY_LEAVE = "oa_leave";
    private static final String PROCESS_KEY_TRIP = "oa_trip";

    @Resource
    private BpmApprovalTemplateService approvalTemplateService;
    @Resource
    private BpmProcessInstanceService processInstanceService;
    @Resource
    private BpmTaskService taskService;
    @Resource
    private BpmProcessDefinitionService processDefinitionService;
    @Resource
    private BpmOALeaveService leaveService;
    @Resource
    private BpmOATripService tripService;
    @Resource
    private MeetingRoomService meetingRoomService;
    @Resource
    private MeetingBookingService meetingBookingService;
    @Resource
    private PersonalScheduleService personalScheduleService;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private DeptService deptService;
    @Resource
    private AdminUserApi adminUserApi;
    @Resource
    private AgentDraftService agentDraftService;

    /* 审批接口已迁移到 AgentApprovalToolController。 */
    /*
        BpmTaskPageReqVO pageReqVO = new BpmTaskPageReqVO();
        pageReqVO.setPageNo(pageNo);
        pageReqVO.setPageSize(pageSize);
        PageResult<Task> pageResult = taskService.getTaskTodoPage(getLoginUserId(), pageReqVO);

        TodoTaskPageResponse response = new TodoTaskPageResponse();
        response.setPageNo(pageNo);
        response.setPageSize(pageSize);
        response.setTotal(pageResult.getTotal());
        if (CollUtil.isEmpty(pageResult.getList())) {
            response.setList(Collections.emptyList());
            return response;
        }

        Map<String, ProcessInstance> processInstanceMap = processInstanceService.getProcessInstanceMap(
                convertSet(pageResult.getList(), Task::getProcessInstanceId));
        Map<Long, AdminUserRespDTO> userMap = adminUserApi.getUserMap(
                convertSet(processInstanceMap.values(), instance -> Long.valueOf(instance.getStartUserId())));
        Map<String, BpmProcessDefinitionInfoDO> processDefinitionInfoMap = processDefinitionService.getProcessDefinitionInfoMap(
                convertSet(pageResult.getList(), Task::getProcessDefinitionId));
        PageResult<BpmTaskRespVO> taskPage = BpmTaskConvert.INSTANCE.buildTodoTaskPage(
                pageResult, processInstanceMap, userMap, processDefinitionInfoMap);
        response.setList(taskPage.getList().stream().map(task -> {
            TodoTask item = new TodoTask();
            item.setTaskId(task.getId());
            item.setName(task.getName());
            item.setProcessInstanceId(task.getProcessInstanceId());
            item.setCreatedTime(task.getCreateTime());
            if (task.getProcessInstance() != null) {
                item.setProcessDefinitionName(task.getProcessInstance().getName());
                if (task.getProcessInstance().getStartUser() != null) {
                    item.setStartUserId(task.getProcessInstance().getStartUser().getId());
                    item.setStartUserName(task.getProcessInstance().getStartUser().getNickname());
                }
            }
            if (task.getAssigneeUser() != null) {
                item.setAssigneeUserId(task.getAssigneeUser().getId());
                item.setAssigneeUserName(task.getAssigneeUser().getNickname());
            }
            return item;
        }).collect(Collectors.toList()));
        return response;
    }

    */
    @GetMapping("/meetings/rooms")
    @Operation(summary = "获取启用中的会议室")
    public MeetingRoomListResponse listMeetingRooms() {
        MeetingRoomListResponse response = new MeetingRoomListResponse();
        response.setRooms(meetingRoomService.getEnableMeetingRoomList().stream().map(roomDO -> {
            MeetingRoom room = new MeetingRoom();
            room.setId(roomDO.getId());
            room.setName(roomDO.getName());
            room.setLocation(roomDO.getLocation());
            return room;
        }).collect(Collectors.toList()));
        return response;
    }

    @PostMapping("/meetings/conflict-check")
    @Operation(summary = "检查会议室冲突")
    public MeetingConflictCheckResponse checkMeetingConflict(@Valid @RequestBody MeetingConflictCheckRequest request) {
        MeetingBookingConflictCheckReqVO reqVO = new MeetingBookingConflictCheckReqVO();
        reqVO.setId(request.getBookingId());
        reqVO.setMeetingRoomId(request.getMeetingRoomId());
        reqVO.setStartTime(request.getStartTime());
        reqVO.setEndTime(request.getEndTime());

        List<MeetingBookingDO> conflicts = meetingBookingService.checkConflictList(reqVO);
        MeetingConflictCheckResponse response = new MeetingConflictCheckResponse();
        response.setHasConflict(CollUtil.isNotEmpty(conflicts));
        response.setConflicts(buildMeetingConflicts(conflicts));
        return response;
    }

    @GetMapping("/meetings/my")
    @Operation(summary = "查询当前用户可见的会议预约")
    public MeetingBookingListResponse listMyMeetingBookings(
            @RequestParam @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime startTime,
            @RequestParam @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime endTime) {
        MeetingBookingListResponse response = new MeetingBookingListResponse();
        response.setBookings(meetingBookingService.getMyCalendarList(getLoginUserId(), startTime, endTime).stream()
                .map(item -> toAgentMeetingBooking(item, getLoginUserId())).collect(Collectors.toList()));
        return response;
    }

    @GetMapping("/meetings/report")
    @Operation(summary = "汇总当前用户会议安排")
    public Map<String, Object> meetingReport(
            @RequestParam @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime startTime,
            @RequestParam @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime endTime) {
        if (!endTime.isAfter(startTime)) throw ServiceExceptionUtil.exception0(400, "报表结束时间必须晚于开始时间");
        List<MeetingBookingDO> bookings = meetingBookingService.getMyCalendarList(getLoginUserId(), startTime, endTime);
        Map<String, Integer> byDay = new LinkedHashMap<>();
        Map<String, Integer> byRoom = new LinkedHashMap<>();
        int totalMinutes = 0;
        List<Map<String, Object>> items = new ArrayList<>();
        for (MeetingBookingDO item : bookings) {
            int minutes = (int) Math.max(0, java.time.Duration.between(item.getStartTime(), item.getEndTime()).toMinutes());
            totalMinutes += minutes;
            String day = item.getStartTime() == null ? "未知日期" : item.getStartTime().toLocalDate().toString();
            byDay.merge(day, 1, Integer::sum);
            MeetingRoomDO room = item.getMeetingRoomId() == null ? null : meetingRoomService.getMeetingRoom(item.getMeetingRoomId());
            byRoom.merge(room == null ? "未指定会议室" : room.getName(), 1, Integer::sum);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("bookingId", item.getId()); row.put("subject", item.getSubject());
            row.put("startTime", item.getStartTime()); row.put("endTime", item.getEndTime());
            row.put("durationMinutes", minutes); row.put("meetingRoomName", room == null ? null : room.getName());
            items.add(row);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportType", "meeting"); result.put("startTime", startTime); result.put("endTime", endTime);
        result.put("total", bookings.size()); result.put("totalMinutes", totalMinutes);
        result.put("byDay", byDay); result.put("byRoom", byRoom); result.put("items", items);
        return result;
    }

    @GetMapping("/meetings/{bookingId}")
    @Operation(summary = "读取当前用户有权查看的会议预约详情")
    public MeetingBookingDetailResponse getMyMeetingBooking(@PathVariable Long bookingId) {
        MeetingBookingDO booking = meetingBookingService.getMeetingBooking(bookingId);
        if (booking == null) throw ServiceExceptionUtil.exception0(404, "会议预约不存在");
        Long userId = getLoginUserId();
        boolean attendee = meetingBookingService.getAttendeeUserIds(bookingId).contains(userId);
        if (!Objects.equals(booking.getApplicantUserId(), userId) && !attendee) {
            throw ServiceExceptionUtil.exception0(403, "无权查看该会议预约");
        }
        return toAgentMeetingBooking(booking, userId);
    }

    @GetMapping("/meetings/book/status")
    @Operation(summary = "查询会议预约提交结果，用于恢复丢失响应")
    public Map<String, Object> getMeetingBookingCommitStatus(
            @RequestParam String draftId,
            @RequestParam String approvalId,
            @RequestParam String operationId) {
        Map<String, Object> result = agentDraftService.findMeetingBookingCommitStatus(
                getTenantId(), getLoginUserId(), draftId, approvalId, operationId);
        if (result == null) {
            throw ServiceExceptionUtil.exception0(404, "会议预约提交结果尚未落库");
        }
        return result;
    }

    @PostMapping("/meetings/book")
    @Operation(summary = "提交已确认的会议预约创建、修改或取消草稿")
    public MeetingBookingCreateResponse createMeetingBooking(@Valid @RequestBody MeetingBookingCreateRequest request) {
        Long userId = getLoginUserId();
        Map<String, Object> submitted = agentDraftService.findSubmittedMeetingBookingResult(
                getTenantId(), userId, request.getDraftId(), request.getApprovalId(), request.getOperationId());
        if (submitted != null) return toMeetingBookingResponse(submitted);
        Map<String, Object> claimedDraft = agentDraftService.claimMeetingBookingDraft(
                getTenantId(), userId, request.getDraftId(), request.getApprovalId(), request.getOperationId());
        boolean storedConflictOverride = agentDraftService.hasStoredConflictOverride(claimedDraft);
        boolean businessCommitted = false;
        try {
            String operation = agentDraftService.meetingBookingOperation(claimedDraft);
            Long bookingId;
            if ("CANCEL".equals(operation)) {
                Long sourceBookingId = agentDraftService.sourceMeetingBookingId(claimedDraft);
                MeetingBookingDO source = meetingBookingService.getMeetingBooking(sourceBookingId);
                validateSourceMeetingBookingSnapshot(claimedDraft, source);
                MeetingBookingCancelReqVO cancelReqVO = new MeetingBookingCancelReqVO();
                cancelReqVO.setId(sourceBookingId);
                cancelReqVO.setCancelReason(String.valueOf(claimedDraft.getOrDefault("cancelReason", "用户取消会议预约")));
                meetingBookingService.cancelMeetingBookingByApplicant(userId, cancelReqVO);
                bookingId = sourceBookingId;
            } else {
                MeetingBookingCreateRequest draftRequest = requestFromDraft(claimedDraft, request);
                agentDraftService.validateMeetingBookingBinding(claimedDraft, draftRequest.getSubject(),
                        draftRequest.getMeetingRoomId(), draftRequest.getStartTime(), draftRequest.getEndTime(),
                        draftRequest.getAttendeeUserIds());
                Long sourceBookingId = "UPDATE".equals(operation)
                        ? agentDraftService.sourceMeetingBookingId(claimedDraft) : null;
                if (sourceBookingId != null) {
                    validateSourceMeetingBookingSnapshot(claimedDraft, meetingBookingService.getMeetingBooking(sourceBookingId));
                }
                validateFinalMeetingBookingAvailability(draftRequest, storedConflictOverride, sourceBookingId);
                MeetingBookingSaveReqVO reqVO = new MeetingBookingSaveReqVO()
                        .setId(sourceBookingId)
                        .setSubject(draftRequest.getSubject())
                        .setMeetingRoomId(draftRequest.getMeetingRoomId())
                        .setStartTime(draftRequest.getStartTime())
                        .setEndTime(draftRequest.getEndTime())
                        .setAttendeeUserIds(draftRequest.getAttendeeUserIds())
                        .setRemark(draftRequest.getRemark())
                        .setForceConflict(storedConflictOverride);
                if (sourceBookingId == null) {
                    bookingId = meetingBookingService.createMeetingBooking(userId, reqVO);
                } else {
                    meetingBookingService.updateMeetingBookingByApplicant(userId, reqVO);
                    bookingId = sourceBookingId;
                }
            }
            businessCommitted = true;
            MeetingBookingCreateResponse response = new MeetingBookingCreateResponse();
            response.setSuccess(true);
            response.setBookingId(bookingId);
            response.setOperation(operation);
            response.setMessage("CREATE".equals(operation) ? "预定成功" : "UPDATE".equals(operation) ? "会议预约已修改" : "会议预约已取消");
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", response.isSuccess());
            result.put("bookingId", response.getBookingId());
            result.put("operation", response.getOperation());
            result.put("message", response.getMessage());
            agentDraftService.markMeetingBookingDraftSubmitted(getTenantId(), userId, request.getDraftId(),
                    request.getOperationId(), result);
            return response;
        } catch (RuntimeException ex) {
            // Once the OA booking has been committed, keep the durable draft in SUBMITTING
            // if the follow-up state update fails. Restoring PENDING here could allow a
            // retry to create a second real booking after a cross-database failure.
            if (!businessCommitted) {
                agentDraftService.restoreMeetingBookingDraftPending(getTenantId(), userId, request.getDraftId(),
                        request.getOperationId());
            }
            throw ex;
        }
    }

    /** 最终提交前重新检查，防止草稿等待用户确认期间出现新的冲突。 */
    private MeetingBookingCreateRequest requestFromDraft(Map<String, Object> draft,
                                                          MeetingBookingCreateRequest ignoredRequest) {
        MeetingBookingCreateRequest request = new MeetingBookingCreateRequest();
        request.setSubject(String.valueOf(draft.get("subject")));
        request.setMeetingRoomId(Long.valueOf(String.valueOf(draft.get("meetingRoomId"))));
        request.setStartTime(parseDraftDateTime(draft.get("startTime")));
        request.setEndTime(parseDraftDateTime(draft.get("endTime")));
        request.setRemark(String.valueOf(draft.getOrDefault("remark", "")));
        Object attendeeValue = draft.get("attendeeUserIds");
        if (attendeeValue instanceof List) {
            request.setAttendeeUserIds(((List<?>) attendeeValue).stream()
                    .filter(Objects::nonNull).map(value -> Long.valueOf(String.valueOf(value)))
                    .distinct().collect(Collectors.toList()));
        } else {
            request.setAttendeeUserIds(Collections.emptyList());
        }
        request.setForceConflict(false);
        return request;
    }

    private java.time.LocalDateTime parseDraftDateTime(Object value) {
        String text = String.valueOf(value).replace('T', ' ');
        for (java.time.format.DateTimeFormatter formatter : List.of(
                java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
                java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))) {
            try { return java.time.LocalDateTime.parse(text, formatter); }
            catch (java.time.format.DateTimeParseException ignored) { }
        }
        throw ServiceExceptionUtil.exception0(409, "AGENT_DRAFT_BINDING_MISMATCH：草稿时间无效");
    }

    private void validateSourceMeetingBookingSnapshot(Map<String, Object> draft, MeetingBookingDO source) {
        if (source == null) {
            throw ServiceExceptionUtil.exception0(404, "来源会议预约不存在或已删除");
        }
        String sourceStart = String.valueOf(draft.getOrDefault("sourceStartTime", ""));
        String sourceEnd = String.valueOf(draft.getOrDefault("sourceEndTime", ""));
        String sourceVersion = String.valueOf(draft.getOrDefault("sourceVersion", ""));
        boolean changedStart = !sourceStart.isEmpty() && !parseDraftDateTime(sourceStart).equals(source.getStartTime());
        boolean changedEnd = !sourceEnd.isEmpty() && !parseDraftDateTime(sourceEnd).equals(source.getEndTime());
        boolean changedVersion = !sourceVersion.isEmpty()
                && !sourceVersion.equals(source.getUpdateTime() == null ? "" : source.getUpdateTime().toString());
        if (changedStart || changedEnd || changedVersion) {
            throw ServiceExceptionUtil.exception0(409, "MEETING_BOOKING_VERSION_CONFLICT：原会议已被修改，请重新确认");
        }
    }

    private void validateFinalMeetingBookingAvailability(MeetingBookingCreateRequest request,
                                                         boolean storedConflictOverride, Long sourceBookingId) {
        MeetingBookingConflictCheckReqVO roomRequest = new MeetingBookingConflictCheckReqVO();
        roomRequest.setId(sourceBookingId);
        roomRequest.setMeetingRoomId(request.getMeetingRoomId());
        roomRequest.setStartTime(request.getStartTime());
        roomRequest.setEndTime(request.getEndTime());
        if (CollUtil.isNotEmpty(meetingBookingService.checkConflictList(roomRequest))) {
            throw ServiceExceptionUtil.exception0(409, "会议室在确认期间已被预约，请重新检查");
        }

        if (storedConflictOverride) return;
        PersonalScheduleCalendarReqVO calendarRequest = new PersonalScheduleCalendarReqVO();
        calendarRequest.setStartTime(request.getStartTime());
        calendarRequest.setEndTime(request.getEndTime());
        for (Long attendeeUserId : Optional.ofNullable(request.getAttendeeUserIds())
                .orElse(Collections.emptyList())) {
            boolean hasPersonalConflict = CollUtil.isNotEmpty(
                    personalScheduleService.getMyCalendarList(attendeeUserId, calendarRequest));
            boolean hasMeetingConflict = meetingBookingService.getMyCalendarList(attendeeUserId,
                    request.getStartTime(), request.getEndTime()).stream()
                    .anyMatch(item -> !Objects.equals(item.getId(), sourceBookingId));
            if (hasPersonalConflict || hasMeetingConflict) {
                throw ServiceExceptionUtil.exception0(409, "参会人在确认期间产生新的日程冲突，请重新检查");
            }
        }
    }

    private MeetingBookingDetailResponse toAgentMeetingBooking(MeetingBookingDO booking, Long currentUserId) {
        MeetingBookingDetailResponse response = new MeetingBookingDetailResponse();
        response.setBookingId(booking.getId());
        response.setSubject(booking.getSubject());
        response.setMeetingRoomId(booking.getMeetingRoomId());
        MeetingRoomDO room = meetingRoomService.getMeetingRoom(booking.getMeetingRoomId());
        response.setMeetingRoomName(room == null ? null : room.getName());
        response.setApplicantUserId(booking.getApplicantUserId());
        response.setStartTime(booking.getStartTime());
        response.setEndTime(booking.getEndTime());
        response.setAttendeeUserIds(meetingBookingService.getAttendeeUserIds(booking.getId()));
        response.setRemark(booking.getRemark());
        response.setStatus(booking.getStatus());
        response.setEditable(Objects.equals(booking.getApplicantUserId(), currentUserId));
        return response;
    }

    private MeetingBookingCreateResponse toMeetingBookingResponse(Map<String, Object> result) {
        MeetingBookingCreateResponse response = new MeetingBookingCreateResponse();
        Object success = result.get("success");
        response.setSuccess(success == null || Boolean.TRUE.equals(success) || "true".equals(String.valueOf(success)));
        Object bookingId = result.get("bookingId");
        if (bookingId != null) response.setBookingId(Long.valueOf(String.valueOf(bookingId)));
        response.setOperation(String.valueOf(result.getOrDefault("operation", "CREATE")));
        response.setMessage(String.valueOf(result.getOrDefault("message", "会议预约已处理")));
        return response;
    }

    /* 日历接口已迁移到 AgentScheduleToolController。
    @GetMapping("/calendar/my")
    @Operation(summary = "获取我的日历")
    public MyCalendarResponse getMyCalendar(@Valid PersonalScheduleCalendarReqVO request) {
        return buildCalendarResponse(getLoginUserId(), request.getStartTime(), request.getEndTime());
    }

    @PostMapping("/calendar/users")
    @Operation(summary = "获取指定参会人员日历")
    public List<UserCalendarResponse> getUsersCalendar(@Valid @RequestBody UserCalendarRequest request) {
        List<Long> userIds = request.getUserIds().stream().filter(Objects::nonNull).distinct().limit(20).collect(Collectors.toList());
        Map<Long, AdminUserDO> userMap = adminUserService.getUserMap(new LinkedHashSet<>(userIds));
        return userIds.stream().filter(userMap::containsKey).map(userId -> {
            UserCalendarResponse response = new UserCalendarResponse();
            response.setUserId(userId);
            response.setUserNickname(userMap.get(userId).getNickname());
            response.setEvents(buildCalendarResponse(userId, request.getStartTime(), request.getEndTime()).getEvents());
            return response;
        }).collect(Collectors.toList());
    }

    private MyCalendarResponse buildCalendarResponse(Long userId, java.time.LocalDateTime startTime,
                                                      java.time.LocalDateTime endTime) {
        PersonalScheduleCalendarReqVO request = new PersonalScheduleCalendarReqVO();
        request.setStartTime(startTime);
        request.setEndTime(endTime);
        List<PersonalScheduleDO> personalSchedules = personalScheduleService.getMyCalendarList(userId, request);
        List<MeetingBookingDO> meetingBookings = meetingBookingService.getMyCalendarList(
                userId, request.getStartTime(), request.getEndTime());
        Map<Long, List<Long>> personalAttendeeMap = personalScheduleService.getAttendeeUserIdsMap(personalSchedules.stream()
                .map(PersonalScheduleDO::getId)
                .collect(Collectors.toList()));
        Map<Long, List<Long>> meetingAttendeeMap = meetingBookingService.getAttendeeUserIdsMap(meetingBookings.stream()
                .map(MeetingBookingDO::getId)
                .collect(Collectors.toList()));
        Map<Long, AdminUserDO> userMap = buildCalendarUserMap(personalAttendeeMap, meetingAttendeeMap);
        Map<Long, MeetingRoomDO> roomMap = meetingBookings.stream()
                .map(MeetingBookingDO::getMeetingRoomId)
                .filter(Objects::nonNull)
                .distinct()
                .map(meetingRoomService::getMeetingRoom)
                .filter(Objects::nonNull)
                .collect(Collectors.toMap(MeetingRoomDO::getId, item -> item));

        List<CalendarEvent> events = new ArrayList<>();
        personalSchedules.forEach(item -> events.add(toPersonalCalendarEvent(item, personalAttendeeMap.get(item.getId()), userMap)));
        meetingBookings.forEach(item -> events.add(toMeetingCalendarEvent(item, meetingAttendeeMap.get(item.getId()), userMap, roomMap.get(item.getMeetingRoomId()))));
        events.sort(Comparator.comparing(CalendarEvent::getStartTime).thenComparing(CalendarEvent::getSourceId));

        MyCalendarResponse response = new MyCalendarResponse();
        response.setEvents(events);
        return response;
    }

    */
    @GetMapping("/users/search")
    @Operation(summary = "搜索启用用户")
    public UserSearchResponse searchUsers(@RequestParam("keyword") String keyword,
                                          @RequestParam(value = "limit", defaultValue = "10") Integer limit) {
        List<AdminUserDO> users = adminUserService.getUserListByStatus(CommonStatusEnum.ENABLE.getStatus()).stream()
                .filter(user -> containsKeyword(user, keyword))
                .limit(Math.max(limit, 1))
                .collect(Collectors.toList());
        Map<Long, DeptDO> deptMap = deptService.getDeptMap(users.stream()
                .map(AdminUserDO::getDeptId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet()));

        UserSearchResponse response = new UserSearchResponse();
        response.setUsers(users.stream().map(user -> {
            UserSimple item = new UserSimple();
            item.setId(user.getId());
            item.setNickname(user.getNickname());
            item.setDeptId(user.getDeptId());
            DeptDO dept = deptMap.get(user.getDeptId());
            item.setDeptName(dept != null ? dept.getName() : null);
            return item;
        }).collect(Collectors.toList()));
        return response;
    }

    @GetMapping("/users/me")
    @Operation(summary = "获取当前 Agent 用户")
    public UserSimple getCurrentUser() {
        AdminUserDO user = adminUserService.getUser(getLoginUserId());
        if (user == null) {
            return null;
        }
        UserSimple response = new UserSimple();
        response.setId(user.getId());
        response.setNickname(user.getNickname());
        response.setDeptId(user.getDeptId());
        if (user.getDeptId() != null) {
            DeptDO dept = deptService.getDept(user.getDeptId());
            response.setDeptName(dept != null ? dept.getName() : null);
        }
        return response;
    }

    private String resolveRequestType(String processDefinitionKey) {
        if (PROCESS_KEY_LEAVE.equals(processDefinitionKey)) {
            return REQUEST_TYPE_LEAVE;
        }
        if (PROCESS_KEY_TRIP.equals(processDefinitionKey)) {
            return REQUEST_TYPE_TRIP;
        }
        return REQUEST_TYPE_GENERIC;
    }

    private String resolveProcessDefinitionId(String requestType, String processDefinitionId) {
        if (StrUtil.isNotBlank(processDefinitionId)) {
            return processDefinitionId;
        }
        if (REQUEST_TYPE_LEAVE.equals(requestType)) {
            return findDefinitionIdByKey(PROCESS_KEY_LEAVE);
        }
        if (REQUEST_TYPE_TRIP.equals(requestType)) {
            return findDefinitionIdByKey(PROCESS_KEY_TRIP);
        }
        throw ServiceExceptionUtil.exception0(400, "generic 请求必须传 processDefinitionId");
    }

    private String findDefinitionIdByKey(String processDefinitionKey) {
        return approvalTemplateService.getApprovalTemplateList(getLoginUserId()).stream()
                .filter(item -> Objects.equals(item.getKey(), processDefinitionKey))
                .map(BpmProcessDefinitionRespVO::getId)
                .findFirst()
                .orElseThrow(() -> ServiceExceptionUtil.exception0(404, "未找到可用流程定义: " + processDefinitionKey));
    }

    private String buildPreviewSummary(List<BpmApprovalDetailRespVO.ActivityNode> nextNodes) {
        if (CollUtil.isEmpty(nextNodes)) {
            return "未识别到后续审批节点";
        }
        return nextNodes.stream().map(BpmApprovalDetailRespVO.ActivityNode::getName)
                .filter(StrUtil::isNotBlank)
                .collect(Collectors.joining(" -> "));
    }

    private Map<String, Object> convertApprovalDetail(BpmApprovalDetailRespVO detail) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", detail.getStatus());
        result.put("processDefinition", detail.getProcessDefinition());
        result.put("processInstance", detail.getProcessInstance());
        result.put("todoTask", detail.getTodoTask());
        result.put("formFieldsPermission", detail.getFormFieldsPermission());
        result.put("activityNodes", detail.getActivityNodes());
        return result;
    }

    private List<MeetingConflict> buildMeetingConflicts(List<MeetingBookingDO> conflicts) {
        if (CollUtil.isEmpty(conflicts)) {
            return Collections.emptyList();
        }
        Map<Long, MeetingRoomDO> roomMap = conflicts.stream()
                .map(MeetingBookingDO::getMeetingRoomId)
                .filter(Objects::nonNull)
                .distinct()
                .map(meetingRoomService::getMeetingRoom)
                .filter(Objects::nonNull)
                .collect(Collectors.toMap(MeetingRoomDO::getId, item -> item));
        Map<Long, AdminUserDO> userMap = adminUserService.getUserMap(conflicts.stream()
                .map(MeetingBookingDO::getApplicantUserId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet()));
        return conflicts.stream().map(conflict -> {
            MeetingConflict item = new MeetingConflict();
            item.setBookingId(conflict.getId());
            item.setMeetingRoomId(conflict.getMeetingRoomId());
            MeetingRoomDO room = roomMap.get(conflict.getMeetingRoomId());
            item.setMeetingRoomName(room != null ? room.getName() : null);
            item.setApplicantUserId(conflict.getApplicantUserId());
            AdminUserDO user = userMap.get(conflict.getApplicantUserId());
            item.setApplicantUserNickname(user != null ? user.getNickname() : null);
            item.setStartTime(conflict.getStartTime());
            item.setEndTime(conflict.getEndTime());
            return item;
        }).collect(Collectors.toList());
    }

    private Map<Long, AdminUserDO> buildCalendarUserMap(Map<Long, List<Long>> personalAttendeeMap,
                                                        Map<Long, List<Long>> meetingAttendeeMap) {
        Set<Long> userIds = new LinkedHashSet<>();
        personalAttendeeMap.values().forEach(userIds::addAll);
        meetingAttendeeMap.values().forEach(userIds::addAll);
        if (CollUtil.isEmpty(userIds)) {
            return Collections.emptyMap();
        }
        return adminUserService.getUserMap(userIds);
    }

    private CalendarEvent toPersonalCalendarEvent(PersonalScheduleDO schedule, List<Long> attendeeUserIds,
                                                  Map<Long, AdminUserDO> userMap) {
        CalendarEvent event = new CalendarEvent();
        event.setSourceType("PERSONAL_SCHEDULE");
        event.setSourceId(schedule.getId());
        event.setEditable(true);
        event.setTitle(schedule.getTitle());
        event.setStartTime(schedule.getStartTime());
        event.setEndTime(schedule.getEndTime());
        event.setLocation(schedule.getLocation());
        event.setDescription(schedule.getDescription());
        event.setOtherParticipants(schedule.getOtherParticipants());
        event.setAttendeeUserIds(defaultList(attendeeUserIds));
        event.setAttendeeUserNicknames(resolveNicknames(attendeeUserIds, userMap));
        return event;
    }

    private CalendarEvent toMeetingCalendarEvent(MeetingBookingDO booking, List<Long> attendeeUserIds,
                                                 Map<Long, AdminUserDO> userMap, MeetingRoomDO room) {
        CalendarEvent event = new CalendarEvent();
        event.setSourceType("MEETING_BOOKING");
        event.setSourceId(booking.getId());
        event.setEditable(false);
        event.setTitle(booking.getSubject());
        event.setStartTime(booking.getStartTime());
        event.setEndTime(booking.getEndTime());
        event.setLocation(room != null ? room.getName() : null);
        event.setDescription(booking.getRemark());
        event.setMeetingRoomId(booking.getMeetingRoomId());
        event.setMeetingRoomName(room != null ? room.getName() : null);
        event.setAttendeeUserIds(defaultList(attendeeUserIds));
        event.setAttendeeUserNicknames(resolveNicknames(attendeeUserIds, userMap));
        return event;
    }

    private List<Long> defaultList(List<Long> values) {
        return values != null ? values : Collections.emptyList();
    }

    private List<String> resolveNicknames(List<Long> attendeeUserIds, Map<Long, AdminUserDO> userMap) {
        if (CollUtil.isEmpty(attendeeUserIds)) {
            return Collections.emptyList();
        }
        return attendeeUserIds.stream()
                .map(userMap::get)
                .filter(Objects::nonNull)
                .map(AdminUserDO::getNickname)
                .collect(Collectors.toList());
    }

    private boolean containsKeyword(AdminUserDO user, String keyword) {
        if (StrUtil.isBlank(keyword)) {
            return true;
        }
        return StrUtil.containsIgnoreCase(StrUtil.blankToDefault(user.getNickname(), ""), keyword)
                || StrUtil.containsIgnoreCase(StrUtil.blankToDefault(user.getUsername(), ""), keyword)
                || StrUtil.containsIgnoreCase(StrUtil.blankToDefault(user.getMobile(), ""), keyword);
    }
}
