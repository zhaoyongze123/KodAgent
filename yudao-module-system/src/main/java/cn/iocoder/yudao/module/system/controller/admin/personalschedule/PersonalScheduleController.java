package cn.iocoder.yudao.module.system.controller.admin.personalschedule;

import cn.hutool.core.collection.CollUtil;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalCalendarEventRespVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleRespVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingRoomService;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - 个人日程")
@RestController
@RequestMapping("/system/personal-schedule")
@Validated
public class PersonalScheduleController {

    private static final String SOURCE_PERSONAL_SCHEDULE = "PERSONAL_SCHEDULE";
    private static final String SOURCE_MEETING_BOOKING = "MEETING_BOOKING";

    @Resource
    private PersonalScheduleService personalScheduleService;
    @Resource
    private MeetingBookingService meetingBookingService;
    @Resource
    private MeetingRoomService meetingRoomService;
    @Resource
    private AdminUserService adminUserService;

    @PostMapping("/create")
    @Operation(summary = "创建个人日程")
    public CommonResult<Long> createPersonalSchedule(@Valid @RequestBody PersonalScheduleSaveReqVO createReqVO) {
        return success(personalScheduleService.createPersonalSchedule(getLoginUserId(), createReqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改个人日程")
    public CommonResult<Boolean> updatePersonalSchedule(@Valid @RequestBody PersonalScheduleSaveReqVO updateReqVO) {
        personalScheduleService.updatePersonalSchedule(getLoginUserId(), updateReqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除个人日程")
    public CommonResult<Boolean> deletePersonalSchedule(@RequestParam("id") Long id) {
        personalScheduleService.deletePersonalSchedule(getLoginUserId(), id);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获得个人日程")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<PersonalScheduleRespVO> getPersonalSchedule(@RequestParam("id") Long id) {
        return success(toScheduleRespVO(personalScheduleService.getPersonalSchedule(getLoginUserId(), id)));
    }

    @GetMapping("/my-calendar")
    @Operation(summary = "获得我的日历事件")
    public CommonResult<List<PersonalCalendarEventRespVO>> getMyCalendar(@Valid PersonalScheduleCalendarReqVO reqVO) {
        Long loginUserId = getLoginUserId();
        List<PersonalScheduleDO> personalSchedules = personalScheduleService.getMyCalendarList(loginUserId, reqVO);
        List<MeetingBookingDO> meetingBookings = meetingBookingService.getMyCalendarList(loginUserId, reqVO.getStartTime(), reqVO.getEndTime());

        Map<Long, List<Long>> personalAttendeeMap = personalScheduleService.getAttendeeUserIdsMap(personalSchedules.stream()
                .map(PersonalScheduleDO::getId)
                .collect(Collectors.toList()));
        Map<Long, List<Long>> meetingAttendeeMap = meetingBookingService.getAttendeeUserIdsMap(meetingBookings.stream()
                .map(MeetingBookingDO::getId)
                .collect(Collectors.toList()));
        Map<Long, AdminUserDO> userMap = buildUserMap(personalAttendeeMap, meetingAttendeeMap);
        Map<Long, MeetingRoomDO> roomMap = buildMeetingRoomMap(meetingBookings);

        List<PersonalCalendarEventRespVO> result = new ArrayList<>();
        personalSchedules.forEach(item -> result.add(toPersonalEvent(item, personalAttendeeMap.get(item.getId()), userMap)));
        meetingBookings.forEach(item -> result.add(toMeetingBookingEvent(item, meetingAttendeeMap.get(item.getId()), userMap, roomMap.get(item.getMeetingRoomId()))));
        result.sort(Comparator.comparing(PersonalCalendarEventRespVO::getStartTime)
                .thenComparing(PersonalCalendarEventRespVO::getSourceId));
        return success(result);
    }

    private PersonalScheduleRespVO toScheduleRespVO(PersonalScheduleDO schedule) {
        if (schedule == null) {
            return null;
        }
        PersonalScheduleRespVO respVO = BeanUtils.toBean(schedule, PersonalScheduleRespVO.class);
        List<Long> attendeeUserIds = personalScheduleService.getAttendeeUserIds(schedule.getId());
        respVO.setAttendeeUserIds(attendeeUserIds);
        if (CollUtil.isNotEmpty(attendeeUserIds)) {
            Map<Long, AdminUserDO> userMap = adminUserService.getUserList(attendeeUserIds).stream()
                    .collect(Collectors.toMap(AdminUserDO::getId, item -> item));
            respVO.setAttendeeUserNicknames(attendeeUserIds.stream()
                    .map(userMap::get)
                    .filter(Objects::nonNull)
                    .map(AdminUserDO::getNickname)
                    .collect(Collectors.toList()));
        } else {
            respVO.setAttendeeUserNicknames(Collections.emptyList());
        }
        return respVO;
    }

    private PersonalCalendarEventRespVO toPersonalEvent(PersonalScheduleDO schedule, List<Long> attendeeUserIds,
                                                         Map<Long, AdminUserDO> userMap) {
        PersonalCalendarEventRespVO respVO = new PersonalCalendarEventRespVO();
        respVO.setSourceType(SOURCE_PERSONAL_SCHEDULE);
        respVO.setSourceId(schedule.getId());
        respVO.setEditable(true);
        respVO.setTitle(schedule.getTitle());
        respVO.setStartTime(schedule.getStartTime());
        respVO.setEndTime(schedule.getEndTime());
        respVO.setLocation(schedule.getLocation());
        respVO.setDescription(schedule.getDescription());
        respVO.setOtherParticipants(schedule.getOtherParticipants());
        respVO.setAttendeeUserIds(defaultList(attendeeUserIds));
        respVO.setAttendeeUserNicknames(resolveNicknames(attendeeUserIds, userMap));
        return respVO;
    }

    private PersonalCalendarEventRespVO toMeetingBookingEvent(MeetingBookingDO booking, List<Long> attendeeUserIds,
                                                               Map<Long, AdminUserDO> userMap, MeetingRoomDO room) {
        PersonalCalendarEventRespVO respVO = new PersonalCalendarEventRespVO();
        respVO.setSourceType(SOURCE_MEETING_BOOKING);
        respVO.setSourceId(booking.getId());
        respVO.setEditable(false);
        respVO.setTitle(booking.getSubject());
        respVO.setStartTime(booking.getStartTime());
        respVO.setEndTime(booking.getEndTime());
        respVO.setLocation(room != null ? room.getName() : null);
        respVO.setDescription(booking.getRemark());
        respVO.setMeetingRoomId(booking.getMeetingRoomId());
        respVO.setMeetingRoomName(room != null ? room.getName() : null);
        respVO.setAttendeeUserIds(defaultList(attendeeUserIds));
        respVO.setAttendeeUserNicknames(resolveNicknames(attendeeUserIds, userMap));
        return respVO;
    }

    private Map<Long, AdminUserDO> buildUserMap(Map<Long, List<Long>> personalAttendeeMap,
                                                Map<Long, List<Long>> meetingAttendeeMap) {
        Set<Long> userIds = new LinkedHashSet<>();
        personalAttendeeMap.values().forEach(userIds::addAll);
        meetingAttendeeMap.values().forEach(userIds::addAll);
        if (CollUtil.isEmpty(userIds)) {
            return Collections.emptyMap();
        }
        return adminUserService.getUserList(new ArrayList<>(userIds)).stream()
                .collect(Collectors.toMap(AdminUserDO::getId, item -> item));
    }

    private Map<Long, MeetingRoomDO> buildMeetingRoomMap(List<MeetingBookingDO> bookings) {
        if (CollUtil.isEmpty(bookings)) {
            return Collections.emptyMap();
        }
        return bookings.stream()
                .map(MeetingBookingDO::getMeetingRoomId)
                .filter(Objects::nonNull)
                .distinct()
                .map(meetingRoomService::getMeetingRoom)
                .filter(Objects::nonNull)
                .collect(Collectors.toMap(MeetingRoomDO::getId, item -> item));
    }

    private List<String> resolveNicknames(List<Long> attendeeUserIds, Map<Long, AdminUserDO> userMap) {
        return defaultList(attendeeUserIds).stream()
                .map(userMap::get)
                .filter(Objects::nonNull)
                .map(AdminUserDO::getNickname)
                .collect(Collectors.toList());
    }

    private List<Long> defaultList(List<Long> values) {
        return values == null ? Collections.emptyList() : values;
    }

}
