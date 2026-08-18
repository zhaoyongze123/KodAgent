package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.*;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.meetingroom.*;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;
import cn.iocoder.yudao.server.controller.agent.vo.OaAgentFacadeVo.*;
import cn.iocoder.yudao.server.service.agent.AgentPersonalScheduleDraftService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "Business Agent Schedule Tools")
@RestController
@RequestMapping("/agent/tools")
@Validated
public class AgentScheduleToolController {
    @Resource private PersonalScheduleService personalScheduleService;
    @Resource private MeetingBookingService meetingBookingService;
    @Resource private MeetingRoomService meetingRoomService;
    @Resource private cn.iocoder.yudao.module.system.service.user.AdminUserService adminUserService;
    @Resource private AgentPersonalScheduleDraftService personalScheduleDraftService;

    @GetMapping("/calendar/my") @Operation(summary = "获取我的日历")
    public MyCalendarResponse getMyCalendar(@Valid PersonalScheduleCalendarReqVO request) { return buildCalendarResponse(getLoginUserId(), request.getStartTime(), request.getEndTime()); }

    @GetMapping("/calendar/report")
    @Operation(summary = "汇总当前用户日程和会议占用")
    public Map<String, Object> calendarReport(@RequestParam @org.springframework.format.annotation.DateTimeFormat(pattern = cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) LocalDateTime startTime,
                                              @RequestParam @org.springframework.format.annotation.DateTimeFormat(pattern = cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) LocalDateTime endTime) {
        if (!endTime.isAfter(startTime)) throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(400, "报表结束时间必须晚于开始时间");
        List<CalendarEvent> events = buildCalendarResponse(getLoginUserId(), startTime, endTime).getEvents();
        Map<String, Integer> bySource = new LinkedHashMap<>();
        Map<String, Integer> byDay = new LinkedHashMap<>();
        int busyMinutes = 0;
        for (CalendarEvent event : events) {
            bySource.merge(event.getSourceType(), 1, Integer::sum);
            String day = event.getStartTime() == null ? "未知日期" : event.getStartTime().toLocalDate().toString();
            byDay.merge(day, 1, Integer::sum);
            if (event.getStartTime() != null && event.getEndTime() != null) {
                busyMinutes += (int) Math.max(0, java.time.Duration.between(event.getStartTime(), event.getEndTime()).toMinutes());
            }
        }
        int conflicts = 0;
        for (int i = 0; i < events.size(); i++) for (int j = i + 1; j < events.size(); j++) {
            CalendarEvent a = events.get(i), b = events.get(j);
            if (a.getStartTime() != null && b.getStartTime() != null && a.getEndTime() != null && b.getEndTime() != null
                    && a.getStartTime().isBefore(b.getEndTime()) && b.getStartTime().isBefore(a.getEndTime())) conflicts++;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportType", "schedule"); result.put("startTime", startTime); result.put("endTime", endTime);
        result.put("total", events.size()); result.put("busyMinutes", busyMinutes); result.put("conflictCount", conflicts);
        result.put("bySource", bySource); result.put("byDay", byDay); result.put("events", events);
        return result;
    }

    @PostMapping("/calendar/users") @Operation(summary = "获取指定参会人员日历")
    public List<UserCalendarResponse> getUsersCalendar(@Valid @RequestBody UserCalendarRequest request) {
        List<Long> ids = request.getUserIds().stream().filter(Objects::nonNull).distinct().limit(20).collect(Collectors.toList());
        Map<Long, AdminUserDO> users = adminUserService.getUserMap(new LinkedHashSet<>(ids));
        return ids.stream().filter(users::containsKey).map(id -> { UserCalendarResponse r = new UserCalendarResponse(); r.setUserId(id); r.setUserNickname(users.get(id).getNickname()); r.setEvents(buildCalendarResponse(id, request.getStartTime(), request.getEndTime()).getEvents()); return r; }).collect(Collectors.toList());
    }

    @GetMapping("/calendar/personal-schedules/{scheduleId}")
    @Operation(summary = "读取我的个人日程详情")
    public Map<String, Object> getPersonalSchedule(@PathVariable Long scheduleId) {
        return personalScheduleDraftService.detail(getLoginUserId(), scheduleId);
    }

    @GetMapping("/calendar/personal-schedules/drafts/{draftId}")
    @Operation(summary = "读取当前用户的个人日程草稿")
    public Map<String, Object> getPersonalScheduleDraft(@PathVariable String draftId) {
        return personalScheduleDraftService.getDraft(cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId(),
                getLoginUserId(), draftId);
    }

    /** Draft creation is allowed; it never writes system_personal_schedule. */
    @PostMapping("/calendar/personal-schedules/drafts")
    @Operation(summary = "创建个人日程草稿")
    public Map<String, Object> savePersonalScheduleDraft(@Valid @RequestBody PersonalScheduleDraftRequest request) {
        return personalScheduleDraftService.save(cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId(),
                getLoginUserId(), request.toMap());
    }

    /** The service atomically verifies APPROVED, owner, source version and conflicts. */
    @PostMapping("/calendar/personal-schedules/commit")
    @Operation(summary = "确认并提交个人日程草稿")
    public Map<String, Object> commitPersonalSchedule(@Valid @RequestBody PersonalScheduleCommitRequest request) {
        return personalScheduleDraftService.commit(cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId(),
                getLoginUserId(), request.getDraftId(), request.getApprovalId(), request.getOperationId());
    }

    @GetMapping("/calendar/personal-schedules/commit/status")
    @Operation(summary = "查询个人日程提交结果，用于恢复丢失响应")
    public Map<String, Object> getPersonalScheduleCommitStatus(
            @RequestParam String draftId,
            @RequestParam String approvalId,
            @RequestParam String operationId) {
        Map<String, Object> result = personalScheduleDraftService.findCommitStatus(
                cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId(),
                getLoginUserId(), draftId, approvalId, operationId);
        if (result == null) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(
                    404, "个人日程提交结果尚未落库");
        }
        return result;
    }

    private MyCalendarResponse buildCalendarResponse(Long userId, LocalDateTime start, LocalDateTime end) {
        PersonalScheduleCalendarReqVO req = new PersonalScheduleCalendarReqVO(); req.setStartTime(start); req.setEndTime(end);
        List<PersonalScheduleDO> schedules = personalScheduleService.getMyCalendarList(userId, req);
        List<MeetingBookingDO> bookings = meetingBookingService.getMyCalendarList(userId, start, end);
        Map<Long, List<Long>> personalAttendees = personalScheduleService.getAttendeeUserIdsMap(schedules.stream().map(PersonalScheduleDO::getId).collect(Collectors.toList()));
        Map<Long, List<Long>> meetingAttendees = meetingBookingService.getAttendeeUserIdsMap(bookings.stream().map(MeetingBookingDO::getId).collect(Collectors.toList()));
        Map<Long, AdminUserDO> users = buildUserMap(personalAttendees, meetingAttendees);
        Map<Long, MeetingRoomDO> rooms = bookings.stream().map(MeetingBookingDO::getMeetingRoomId).filter(Objects::nonNull).distinct().map(meetingRoomService::getMeetingRoom).filter(Objects::nonNull).collect(Collectors.toMap(MeetingRoomDO::getId, x -> x));
        List<CalendarEvent> events = new ArrayList<>();
        schedules.forEach(x -> events.add(personalEvent(x, personalAttendees.get(x.getId()), users)));
        bookings.forEach(x -> events.add(meetingEvent(x, meetingAttendees.get(x.getId()), users,
                rooms.get(x.getMeetingRoomId()), userId)));
        events.sort(Comparator.comparing(CalendarEvent::getStartTime).thenComparing(CalendarEvent::getSourceId));
        MyCalendarResponse response = new MyCalendarResponse(); response.setEvents(events); return response;
    }

    private Map<Long, AdminUserDO> buildUserMap(Map<Long, List<Long>> a, Map<Long, List<Long>> b) { Set<Long> ids = new LinkedHashSet<>(); a.values().forEach(ids::addAll); b.values().forEach(ids::addAll); return ids.isEmpty() ? Collections.emptyMap() : adminUserService.getUserMap(ids); }
    private CalendarEvent personalEvent(PersonalScheduleDO x, List<Long> ids, Map<Long, AdminUserDO> users) { CalendarEvent e = new CalendarEvent(); e.setSourceType("PERSONAL_SCHEDULE"); e.setSourceId(x.getId()); e.setEditable(true); e.setTitle(x.getTitle()); e.setStartTime(x.getStartTime()); e.setEndTime(x.getEndTime()); e.setLocation(x.getLocation()); e.setDescription(x.getDescription()); e.setOtherParticipants(x.getOtherParticipants()); e.setAttendeeUserIds(defaultIds(ids)); e.setAttendeeUserNicknames(names(ids, users)); return e; }
    private CalendarEvent meetingEvent(MeetingBookingDO x, List<Long> ids, Map<Long, AdminUserDO> users,
                                       MeetingRoomDO room, Long currentUserId) { CalendarEvent e = new CalendarEvent(); e.setSourceType("MEETING_BOOKING"); e.setSourceId(x.getId()); e.setEditable(Objects.equals(x.getApplicantUserId(), currentUserId)); e.setTitle(x.getSubject()); e.setStartTime(x.getStartTime()); e.setEndTime(x.getEndTime()); e.setLocation(room == null ? null : room.getName()); e.setDescription(x.getRemark()); e.setMeetingRoomId(x.getMeetingRoomId()); e.setMeetingRoomName(room == null ? null : room.getName()); e.setAttendeeUserIds(defaultIds(ids)); e.setAttendeeUserNicknames(names(ids, users)); return e; }
    private List<Long> defaultIds(List<Long> ids) { return ids == null ? Collections.emptyList() : ids; }
    private List<String> names(List<Long> ids, Map<Long, AdminUserDO> users) { return ids == null ? Collections.emptyList() : ids.stream().map(users::get).filter(Objects::nonNull).map(AdminUserDO::getNickname).collect(Collectors.toList()); }
}
