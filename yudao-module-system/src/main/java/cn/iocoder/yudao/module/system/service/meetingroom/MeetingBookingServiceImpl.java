package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.*;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingAttendeeDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingBookingAttendeeMapper;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingBookingMapper;
import cn.iocoder.yudao.module.system.framework.notify.SystemMeetingBookingNotifyTemplateInitRunner;
import cn.iocoder.yudao.module.system.service.notify.NotifySendService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Slf4j
@Validated
public class MeetingBookingServiceImpl implements MeetingBookingService {

    private static final Integer STATUS_ACTIVE = 1;
    private static final Integer STATUS_CANCELLED = 2;
    private static final Integer CANCEL_TYPE_USER = 1;
    private static final Integer CANCEL_TYPE_ADMIN = 2;

    @Resource
    private MeetingBookingMapper meetingBookingMapper;
    @Resource
    private MeetingBookingAttendeeMapper meetingBookingAttendeeMapper;
    @Resource
    private MeetingRoomService meetingRoomService;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private NotifySendService notifySendService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createMeetingBooking(Long operatorUserId, MeetingBookingSaveReqVO createReqVO) {
        validateSaveReqVO(createReqVO, null, false);
        MeetingBookingDO booking = BeanUtils.toBean(createReqVO, MeetingBookingDO.class);
        booking.setApplicantUserId(operatorUserId);
        booking.setStatus(STATUS_ACTIVE);
        meetingBookingMapper.insert(booking);
        saveAttendees(booking.getId(), createReqVO.getAttendeeUserIds());
        return booking.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateMeetingBookingByAdmin(Long operatorUserId, MeetingBookingSaveReqVO updateReqVO) {
        MeetingBookingDO existed = validateSaveReqVO(updateReqVO, updateReqVO.getId(), true);
        MeetingBookingDO updateObj = BeanUtils.toBean(updateReqVO, MeetingBookingDO.class);
        updateObj.setApplicantUserId(existed.getApplicantUserId());
        updateObj.setStatus(existed.getStatus());
        updateObj.setCancelReason(existed.getCancelReason());
        updateObj.setCancelType(existed.getCancelType());
        meetingBookingMapper.updateById(updateObj);
        saveAttendees(updateReqVO.getId(), updateReqVO.getAttendeeUserIds());
        if (!Objects.equals(operatorUserId, existed.getApplicantUserId())) {
            sendUpdateNotice(existed.getApplicantUserId(), updateObj);
        }
        notifyConflictUsers(updateReqVO.getId(), updateObj);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateMeetingBookingByApplicant(Long operatorUserId, MeetingBookingSaveReqVO updateReqVO) {
        MeetingBookingDO existed = validateSaveReqVO(updateReqVO, updateReqVO.getId(), false);
        validateApplicantOperation(operatorUserId, existed);
        MeetingBookingDO updateObj = BeanUtils.toBean(updateReqVO, MeetingBookingDO.class);
        updateObj.setApplicantUserId(existed.getApplicantUserId());
        updateObj.setStatus(existed.getStatus());
        updateObj.setCancelReason(existed.getCancelReason());
        updateObj.setCancelType(existed.getCancelType());
        meetingBookingMapper.updateById(updateObj);
        saveAttendees(updateReqVO.getId(), updateReqVO.getAttendeeUserIds());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void cancelMeetingBookingByApplicant(Long operatorUserId, MeetingBookingCancelReqVO cancelReqVO) {
        MeetingBookingDO booking = validateMeetingBookingExists(cancelReqVO.getId());
        validateApplicantOperation(operatorUserId, booking);
        cancelBooking(booking, cancelReqVO.getCancelReason(), CANCEL_TYPE_USER);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteMeetingBookingByAdmin(Long operatorUserId, MeetingBookingCancelReqVO cancelReqVO) {
        MeetingBookingDO booking = validateMeetingBookingExists(cancelReqVO.getId());
        cancelBooking(booking, cancelReqVO.getCancelReason(), CANCEL_TYPE_ADMIN);
        if (!Objects.equals(operatorUserId, booking.getApplicantUserId())) {
            sendCancelNotice(booking.getApplicantUserId(), booking, cancelReqVO.getCancelReason());
        }
    }

    @Override
    public MeetingBookingDO getMeetingBooking(Long id) {
        return meetingBookingMapper.selectById(id);
    }

    @Override
    public PageResult<MeetingBookingDO> getMeetingBookingPage(MeetingBookingPageReqVO pageReqVO) {
        return meetingBookingMapper.selectPage(pageReqVO);
    }

    @Override
    public PageResult<MeetingBookingDO> getMyMeetingBookingPage(Long applicantUserId, MeetingBookingPageReqVO pageReqVO) {
        return meetingBookingMapper.selectMyPage(applicantUserId, pageReqVO);
    }

    @Override
    public List<MeetingBookingDO> getWeekScheduleList(MeetingBookingScheduleReqVO reqVO) {
        validateScheduleRange(reqVO);
        return meetingBookingMapper.selectScheduleList(reqVO);
    }

    @Override
    public List<MeetingBookingDO> getMonthScheduleList(MeetingBookingScheduleReqVO reqVO) {
        validateScheduleRange(reqVO);
        return meetingBookingMapper.selectScheduleList(reqVO);
    }

    @Override
    public List<MeetingBookingDO> checkConflictList(MeetingBookingConflictCheckReqVO reqVO) {
        validateTimeSlot(reqVO.getStartTime(), reqVO.getEndTime());
        return meetingBookingMapper.selectConflictList(reqVO.getMeetingRoomId(), reqVO.getStartTime(), reqVO.getEndTime(), reqVO.getId());
    }

    @Override
    public List<Long> getAttendeeUserIds(Long bookingId) {
        return meetingBookingAttendeeMapper.selectListByBookingId(bookingId).stream()
                .map(MeetingBookingAttendeeDO::getUserId)
                .collect(Collectors.toList());
    }

    @Override
    public Map<Long, List<Long>> getAttendeeUserIdsMap(List<Long> bookingIds) {
        if (CollUtil.isEmpty(bookingIds)) {
            return Collections.emptyMap();
        }
        return meetingBookingAttendeeMapper.selectListByBookingIds(bookingIds).stream()
                .collect(Collectors.groupingBy(MeetingBookingAttendeeDO::getBookingId,
                        LinkedHashMap::new,
                        Collectors.mapping(MeetingBookingAttendeeDO::getUserId, Collectors.toList())));
    }

    @Override
    public List<MeetingBookingDO> getMyCalendarList(Long applicantUserId, LocalDateTime startTime, LocalDateTime endTime) {
        LinkedHashMap<Long, MeetingBookingDO> bookingMap = new LinkedHashMap<>();
        meetingBookingMapper.selectMyCalendarList(applicantUserId, startTime, endTime)
                .forEach(item -> bookingMap.put(item.getId(), item));
        List<Long> attendeeBookingIds = meetingBookingAttendeeMapper.selectListByUserId(applicantUserId).stream()
                .map(MeetingBookingAttendeeDO::getBookingId)
                .filter(Objects::nonNull)
                .distinct()
                .collect(Collectors.toList());
        if (CollUtil.isNotEmpty(attendeeBookingIds)) {
            meetingBookingMapper.selectCalendarListByIds(attendeeBookingIds, startTime, endTime)
                    .forEach(item -> bookingMap.put(item.getId(), item));
        }
        return bookingMap.values().stream()
                .sorted(Comparator.comparing(MeetingBookingDO::getStartTime)
                        .thenComparing(MeetingBookingDO::getId))
                .collect(Collectors.toList());
    }

    private MeetingBookingDO validateSaveReqVO(MeetingBookingSaveReqVO reqVO, Long excludeId, boolean allowStartedForAdmin) {
        MeetingBookingDO existed = excludeId != null ? validateMeetingBookingExists(excludeId) : null;
        if (existed != null && !allowStartedForAdmin && LocalDateTime.now().isAfter(existed.getStartTime())) {
            throw exception(MEETING_BOOKING_STARTED_CANNOT_OPERATE);
        }
        MeetingRoomDO room = validateMeetingRoomAvailable(reqVO.getMeetingRoomId());
        validateTimeSlot(reqVO.getStartTime(), reqVO.getEndTime());
        List<MeetingBookingDO> conflicts = meetingBookingMapper.selectConflictList(room.getId(), reqVO.getStartTime(), reqVO.getEndTime(), excludeId);
        if (CollUtil.isNotEmpty(conflicts) && !Boolean.TRUE.equals(reqVO.getForceConflict())) {
            throw exception(MEETING_BOOKING_CONFLICT_EXISTS);
        }
        return existed;
    }

    private MeetingRoomDO validateMeetingRoomAvailable(Long roomId) {
        MeetingRoomDO room = meetingRoomService.getMeetingRoom(roomId);
        if (room == null) {
            throw exception(MEETING_ROOM_NOT_EXISTS);
        }
        if (!Objects.equals(room.getStatus(), CommonStatusEnum.ENABLE.getStatus())) {
            throw exception(MEETING_ROOM_DISABLED, room.getName());
        }
        return room;
    }

    private void validateTimeSlot(LocalDateTime startTime, LocalDateTime endTime) {
        LocalDateTime now = LocalDateTime.now();
        log.info("[validateTimeSlot] startTime={}, endTime={}, now={}", startTime, endTime, now);
        if (startTime == null || endTime == null || !startTime.isBefore(endTime)) {
            throw exception(MEETING_BOOKING_TIME_INVALID);
        }
        if (!Objects.equals(startTime.toLocalDate(), endTime.toLocalDate())) {
            throw exception(MEETING_BOOKING_CROSS_DAY_NOT_SUPPORTED);
        }
        if (startTime.getMinute() != 0 || endTime.getMinute() != 0 || startTime.getSecond() != 0 || endTime.getSecond() != 0) {
            throw exception(MEETING_BOOKING_TIME_SLOT_INVALID);
        }
        if (LocalDateTimeUtil.between(startTime, endTime).toHours() != 2) {
            throw exception(MEETING_BOOKING_TIME_SLOT_INVALID);
        }
        if (endTime.isBefore(now)) {
            throw exception(MEETING_BOOKING_TIME_INVALID);
        }
    }

    private void validateApplicantOperation(Long operatorUserId, MeetingBookingDO booking) {
        if (!Objects.equals(operatorUserId, booking.getApplicantUserId())) {
            throw exception(MEETING_BOOKING_NOT_OWNER);
        }
        if (!LocalDateTime.now().isBefore(booking.getStartTime())) {
            throw exception(MEETING_BOOKING_STARTED_CANNOT_OPERATE);
        }
    }

    private MeetingBookingDO validateMeetingBookingExists(Long id) {
        MeetingBookingDO booking = meetingBookingMapper.selectById(id);
        if (booking == null) {
            throw exception(MEETING_BOOKING_NOT_EXISTS);
        }
        return booking;
    }

    private void cancelBooking(MeetingBookingDO booking, String cancelReason, Integer cancelType) {
        if (Objects.equals(booking.getStatus(), STATUS_CANCELLED)) {
            return;
        }
        MeetingBookingDO updateObj = new MeetingBookingDO();
        updateObj.setId(booking.getId());
        updateObj.setStatus(STATUS_CANCELLED);
        updateObj.setCancelReason(cancelReason);
        updateObj.setCancelType(cancelType);
        meetingBookingMapper.updateById(updateObj);
    }

    private void saveAttendees(Long bookingId, List<Long> attendeeUserIds) {
        meetingBookingAttendeeMapper.deleteByBookingId(bookingId);
        if (CollUtil.isEmpty(attendeeUserIds)) {
            return;
        }
        attendeeUserIds.stream()
                .filter(Objects::nonNull)
                .distinct()
                .forEach(userId -> {
                    MeetingBookingAttendeeDO attendee = new MeetingBookingAttendeeDO();
                    attendee.setBookingId(bookingId);
                    attendee.setUserId(userId);
                    meetingBookingAttendeeMapper.insert(attendee);
                });
    }

    private void notifyConflictUsers(Long bookingId, MeetingBookingDO booking) {
        List<MeetingBookingDO> conflicts = meetingBookingMapper.selectConflictList(
                booking.getMeetingRoomId(), booking.getStartTime(), booking.getEndTime(), bookingId);
        if (CollUtil.isEmpty(conflicts)) {
            return;
        }
        String roomName = Optional.ofNullable(meetingRoomService.getMeetingRoom(booking.getMeetingRoomId()))
                .map(MeetingRoomDO::getName)
                .orElse("");
        conflicts.stream()
                .map(MeetingBookingDO::getApplicantUserId)
                .filter(Objects::nonNull)
                .distinct()
                .forEach(userId -> notifySendService.sendSingleNotifyToAdmin(userId,
                        SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_CONFLICT_NOTICE_TEMPLATE_CODE,
                        buildConflictTemplateParams(booking, roomName)));
    }

    private void sendUpdateNotice(Long applicantUserId, MeetingBookingDO booking) {
        String roomName = Optional.ofNullable(meetingRoomService.getMeetingRoom(booking.getMeetingRoomId()))
                .map(MeetingRoomDO::getName)
                .orElse("");
        notifySendService.sendSingleNotifyToAdmin(applicantUserId,
                SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_UPDATE_NOTICE_TEMPLATE_CODE,
                buildUpdateTemplateParams(booking, roomName));
    }

    private void sendCancelNotice(Long applicantUserId, MeetingBookingDO booking, String cancelReason) {
        String roomName = Optional.ofNullable(meetingRoomService.getMeetingRoom(booking.getMeetingRoomId()))
                .map(MeetingRoomDO::getName)
                .orElse("");
        Map<String, Object> params = buildUpdateTemplateParams(booking, roomName);
        params.put("cancelReason", Optional.ofNullable(cancelReason).orElse("管理员取消"));
        notifySendService.sendSingleNotifyToAdmin(applicantUserId,
                SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_CANCEL_NOTICE_TEMPLATE_CODE,
                params);
    }

    private Map<String, Object> buildUpdateTemplateParams(MeetingBookingDO booking, String roomName) {
        Map<String, Object> params = new HashMap<>();
        params.put("subject", booking.getSubject());
        params.put("roomName", roomName);
        params.put("startTime", String.valueOf(booking.getStartTime()));
        params.put("endTime", String.valueOf(booking.getEndTime()));
        return params;
    }

    private Map<String, Object> buildConflictTemplateParams(MeetingBookingDO booking, String roomName) {
        Map<String, Object> params = buildUpdateTemplateParams(booking, roomName);
        params.put("bookingId", String.valueOf(booking.getId()));
        return params;
    }

    private void validateScheduleRange(MeetingBookingScheduleReqVO reqVO) {
        if (reqVO.getStartTime() == null || reqVO.getEndTime() == null || !reqVO.getStartTime().isBefore(reqVO.getEndTime())) {
            throw exception(MEETING_BOOKING_TIME_INVALID);
        }
        LocalDate start = reqVO.getStartTime().toLocalDate();
        LocalDate end = reqVO.getEndTime().toLocalDate();
        if (end.isBefore(start)) {
            throw exception(MEETING_BOOKING_TIME_INVALID);
        }
    }

}
