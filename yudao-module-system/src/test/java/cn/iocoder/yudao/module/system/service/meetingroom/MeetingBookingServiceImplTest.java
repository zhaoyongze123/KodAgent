package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.test.core.ut.BaseDbUnitTest;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingCancelReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingConflictCheckReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingAttendeeDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingRoomDO;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingBookingAttendeeMapper;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingBookingMapper;
import cn.iocoder.yudao.module.system.dal.mysql.meetingroom.MeetingRoomMapper;
import cn.iocoder.yudao.module.system.framework.notify.SystemMeetingBookingNotifyTemplateInitRunner;
import cn.iocoder.yudao.module.system.service.notify.NotifySendService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.test.core.util.AssertUtils.assertServiceException;
import static cn.iocoder.yudao.framework.test.core.util.RandomUtils.randomLongId;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@Import({MeetingBookingServiceImpl.class, MeetingRoomServiceImpl.class})
class MeetingBookingServiceImplTest extends BaseDbUnitTest {

    @Resource
    private MeetingBookingServiceImpl meetingBookingService;
    @Resource
    private MeetingBookingMapper meetingBookingMapper;
    @Resource
    private MeetingBookingAttendeeMapper attendeeMapper;
    @Resource
    private MeetingRoomMapper meetingRoomMapper;

    @MockBean
    private AdminUserService adminUserService;
    @MockBean
    private NotifySendService notifySendService;

    @Test
    void testCreateMeetingBooking_success() {
        MeetingRoomDO room = insertMeetingRoom("A-01");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, false, List.of(11L, 12L, 12L));

        Long bookingId = meetingBookingService.createMeetingBooking(100L, reqVO);

        MeetingBookingDO booking = meetingBookingMapper.selectById(bookingId);
        assertNotNull(booking);
        assertEquals(100L, booking.getApplicantUserId());
        assertEquals(1, booking.getStatus());
        assertEquals(2, attendeeMapper.selectListByBookingId(bookingId).size());
    }

    @Test
    void testCreateMeetingBooking_timeSlotInvalid() {
        MeetingRoomDO room = insertMeetingRoom("A-02");
        LocalDateTime startTime = nextHourPlusDays(1).plusMinutes(30);
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, false, List.of());

        assertServiceException(() -> meetingBookingService.createMeetingBooking(100L, reqVO),
                MEETING_BOOKING_TIME_SLOT_INVALID);
    }

    @Test
    void testCreateMeetingBooking_crossDayNotSupported() {
        MeetingRoomDO room = insertMeetingRoom("A-03");
        LocalDateTime startTime = LocalDateTime.now().plusDays(1)
                .withHour(23).withMinute(0).withSecond(0).withNano(0);
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, false, List.of());

        assertServiceException(() -> meetingBookingService.createMeetingBooking(100L, reqVO),
                MEETING_BOOKING_CROSS_DAY_NOT_SUPPORTED);
    }

    @Test
    void testCreateMeetingBooking_conflictExists() {
        MeetingRoomDO room = insertMeetingRoom("A-04");
        LocalDateTime startTime = nextHourPlusDays(1);
        insertBooking(room.getId(), 200L, startTime, 1, null, null, "existing");
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, false, List.of());

        assertServiceException(() -> meetingBookingService.createMeetingBooking(100L, reqVO),
                MEETING_BOOKING_CONFLICT_EXISTS);
    }

    @Test
    void testCreateMeetingBooking_forceConflictSuccess() {
        MeetingRoomDO room = insertMeetingRoom("A-05");
        LocalDateTime startTime = nextHourPlusDays(1);
        insertBooking(room.getId(), 200L, startTime, 1, null, null, "existing");
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, true, List.of());

        Long bookingId = meetingBookingService.createMeetingBooking(100L, reqVO);

        assertNotNull(meetingBookingMapper.selectById(bookingId));
    }

    @Test
    void testUpdateMeetingBookingByApplicant_notOwner() {
        MeetingRoomDO room = insertMeetingRoom("A-06");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO booking = insertBooking(room.getId(), 200L, startTime, 1, null, null, "origin");
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime.plusDays(1), false, List.of());
        reqVO.setId(booking.getId());

        assertServiceException(() -> meetingBookingService.updateMeetingBookingByApplicant(100L, reqVO),
                MEETING_BOOKING_NOT_OWNER);
    }

    @Test
    void testUpdateMeetingBookingByApplicant_startedCannotOperate() {
        MeetingRoomDO room = insertMeetingRoom("A-07");
        LocalDateTime startTime = LocalDateTime.now().minusHours(1).withMinute(0).withSecond(0).withNano(0);
        MeetingBookingDO booking = insertBooking(room.getId(), 100L, startTime, 1, null, null, "started");
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), nextHourPlusDays(1), false, List.of());
        reqVO.setId(booking.getId());

        assertServiceException(() -> meetingBookingService.updateMeetingBookingByApplicant(100L, reqVO),
                MEETING_BOOKING_STARTED_CANNOT_OPERATE);
    }

    @Test
    void testDeleteMeetingBookingByAdmin_cancelAndNotify() {
        MeetingRoomDO room = insertMeetingRoom("A-08");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO booking = insertBooking(room.getId(), 200L, startTime, 1, null, null, "notify");

        MeetingBookingCancelReqVO reqVO = new MeetingBookingCancelReqVO();
        reqVO.setId(booking.getId());
        reqVO.setCancelReason("管理员取消");
        meetingBookingService.deleteMeetingBookingByAdmin(1L, reqVO);

        MeetingBookingDO updated = meetingBookingMapper.selectById(booking.getId());
        assertEquals(2, updated.getStatus());
        assertEquals(2, updated.getCancelType());
        assertEquals("管理员取消", updated.getCancelReason());
        verify(notifySendService).sendSingleNotifyToAdmin(eq(200L),
                eq(SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_CANCEL_NOTICE_TEMPLATE_CODE),
                argThat((Map<String, Object> params) -> "管理员取消".equals(params.get("cancelReason"))
                        && room.getName().equals(params.get("roomName"))));
    }

    @Test
    void testDeleteMeetingBookingByAdmin_selfNoNotify() {
        MeetingRoomDO room = insertMeetingRoom("A-09");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO booking = insertBooking(room.getId(), 1L, startTime, 1, null, null, "self");

        MeetingBookingCancelReqVO reqVO = new MeetingBookingCancelReqVO();
        reqVO.setId(booking.getId());
        reqVO.setCancelReason("自己取消");
        meetingBookingService.deleteMeetingBookingByAdmin(1L, reqVO);

        verify(notifySendService, never()).sendSingleNotifyToAdmin(eq(1L),
                eq(SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_CANCEL_NOTICE_TEMPLATE_CODE),
                argThat((Map<String, Object> params) -> true));
    }

    @Test
    void testUpdateMeetingBookingByAdmin_conflictNotify() {
        MeetingRoomDO room = insertMeetingRoom("A-10");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO target = insertBooking(room.getId(), 200L, startTime.plusDays(1), 1, null, null, "target");
        insertBooking(room.getId(), 300L, startTime, 1, null, null, "conflict");
        MeetingBookingSaveReqVO reqVO = createReqVO(room.getId(), startTime, true, List.of(21L));
        reqVO.setId(target.getId());
        reqVO.setSubject("管理员改期");

        meetingBookingService.updateMeetingBookingByAdmin(1L, reqVO);

        MeetingBookingDO updated = meetingBookingMapper.selectById(target.getId());
        assertEquals(startTime, updated.getStartTime());
        assertTrue(attendeeMapper.selectListByBookingId(target.getId()).stream()
                .map(MeetingBookingAttendeeDO::getUserId).anyMatch(userId -> userId.equals(21L)));
        verify(notifySendService).sendSingleNotifyToAdmin(eq(200L),
                eq(SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_UPDATE_NOTICE_TEMPLATE_CODE),
                argThat((Map<String, Object> params) -> "管理员改期".equals(params.get("subject"))));
        verify(notifySendService).sendSingleNotifyToAdmin(eq(300L),
                eq(SystemMeetingBookingNotifyTemplateInitRunner.MEETING_BOOKING_CONFLICT_NOTICE_TEMPLATE_CODE),
                argThat((Map<String, Object> params) -> String.valueOf(target.getId()).equals(params.get("bookingId"))));
    }

    @Test
    void testCheckConflictList_onlyActive() {
        MeetingRoomDO room = insertMeetingRoom("A-11");
        LocalDateTime startTime = nextHourPlusDays(1);
        insertBooking(room.getId(), 200L, startTime, 1, null, null, "active");
        insertBooking(room.getId(), 201L, startTime, 2, "已取消", 2, "cancelled");
        MeetingBookingConflictCheckReqVO reqVO = new MeetingBookingConflictCheckReqVO();
        reqVO.setMeetingRoomId(room.getId());
        reqVO.setStartTime(startTime);
        reqVO.setEndTime(startTime.plusHours(2));

        List<MeetingBookingDO> result = meetingBookingService.checkConflictList(reqVO);

        assertEquals(1, result.size());
        assertEquals("active", result.get(0).getSubject());
    }

    @Test
    void testGetMyCalendarList_includeAttendeeBookings() {
        MeetingRoomDO room = insertMeetingRoom("A-11-A");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO ownBooking = insertBooking(room.getId(), 100L, startTime, 1, null, null, "own");
        MeetingBookingDO attendeeBooking = insertBooking(room.getId(), 200L, startTime.plusHours(2), 1, null, null, "attendee");
        MeetingBookingAttendeeDO attendee = new MeetingBookingAttendeeDO();
        attendee.setBookingId(attendeeBooking.getId());
        attendee.setUserId(100L);
        attendeeMapper.insert(attendee);

        List<MeetingBookingDO> result = meetingBookingService.getMyCalendarList(
                100L, startTime.minusHours(1), startTime.plusDays(1));

        assertEquals(2, result.size());
        assertEquals(List.of(ownBooking.getId(), attendeeBooking.getId()),
                result.stream().map(MeetingBookingDO::getId).collect(java.util.stream.Collectors.toList()));
    }

    @Test
    void testCancelMeetingBookingByApplicant_success() {
        MeetingRoomDO room = insertMeetingRoom("A-12");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO booking = insertBooking(room.getId(), 200L, startTime, 1, null, null, "my");
        MeetingBookingCancelReqVO reqVO = new MeetingBookingCancelReqVO();
        reqVO.setId(booking.getId());
        reqVO.setCancelReason("自己取消");

        meetingBookingService.cancelMeetingBookingByApplicant(200L, reqVO);

        MeetingBookingDO updated = meetingBookingMapper.selectById(booking.getId());
        assertEquals(2, updated.getStatus());
        assertEquals(1, updated.getCancelType());
        assertEquals("自己取消", updated.getCancelReason());
    }

    @Test
    void testGetAttendeeUserIds_success() {
        MeetingRoomDO room = insertMeetingRoom("A-13");
        LocalDateTime startTime = nextHourPlusDays(1);
        MeetingBookingDO booking = insertBooking(room.getId(), 200L, startTime, 1, null, null, "attendee");
        attendeeMapper.insert(new MeetingBookingAttendeeDO().setBookingId(booking.getId()).setUserId(10L));
        attendeeMapper.insert(new MeetingBookingAttendeeDO().setBookingId(booking.getId()).setUserId(11L));

        List<Long> attendeeUserIds = meetingBookingService.getAttendeeUserIds(booking.getId());

        assertEquals(List.of(10L, 11L), attendeeUserIds);
    }

    private MeetingRoomDO insertMeetingRoom(String name) {
        MeetingRoomDO room = new MeetingRoomDO();
        room.setName(name);
        room.setLocation("3F");
        room.setCapacity(10);
        room.setEquipment("projector");
        room.setRemark("test");
        room.setStatus(CommonStatusEnum.ENABLE.getStatus());
        room.setSort(1);
        meetingRoomMapper.insert(room);
        return room;
    }

    private MeetingBookingDO insertBooking(Long roomId, Long applicantUserId, LocalDateTime startTime,
                                           Integer status, String cancelReason, Integer cancelType, String subject) {
        MeetingBookingDO booking = new MeetingBookingDO();
        booking.setSubject(subject);
        booking.setMeetingRoomId(roomId);
        booking.setStartTime(startTime);
        booking.setEndTime(startTime.plusHours(2));
        booking.setApplicantUserId(applicantUserId);
        booking.setRemark("remark");
        booking.setStatus(status);
        booking.setForceConflict(false);
        booking.setCancelReason(cancelReason);
        booking.setCancelType(cancelType);
        meetingBookingMapper.insert(booking);
        return booking;
    }

    private MeetingBookingSaveReqVO createReqVO(Long roomId, LocalDateTime startTime, boolean forceConflict, List<Long> attendeeUserIds) {
        MeetingBookingSaveReqVO reqVO = new MeetingBookingSaveReqVO();
        reqVO.setSubject("会议主题-" + randomLongId());
        reqVO.setMeetingRoomId(roomId);
        reqVO.setStartTime(startTime);
        reqVO.setEndTime(startTime.plusHours(2));
        reqVO.setAttendeeUserIds(attendeeUserIds);
        reqVO.setRemark("测试备注");
        reqVO.setForceConflict(forceConflict);
        return reqVO;
    }

    private LocalDateTime nextHourPlusDays(int days) {
        return LocalDateTime.now().plusDays(days).plusHours(1)
                .withMinute(0).withSecond(0).withNano(0);
    }
}
