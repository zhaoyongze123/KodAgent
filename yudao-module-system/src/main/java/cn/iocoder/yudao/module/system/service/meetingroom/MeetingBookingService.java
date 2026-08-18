package cn.iocoder.yudao.module.system.service.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.*;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;

import javax.validation.Valid;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

public interface MeetingBookingService {

    Long createMeetingBooking(Long operatorUserId, @Valid MeetingBookingSaveReqVO createReqVO);

    void updateMeetingBookingByAdmin(Long operatorUserId, @Valid MeetingBookingSaveReqVO updateReqVO);

    void updateMeetingBookingByApplicant(Long operatorUserId, @Valid MeetingBookingSaveReqVO updateReqVO);

    void cancelMeetingBookingByApplicant(Long operatorUserId, @Valid MeetingBookingCancelReqVO cancelReqVO);

    void deleteMeetingBookingByAdmin(Long operatorUserId, @Valid MeetingBookingCancelReqVO cancelReqVO);

    MeetingBookingDO getMeetingBooking(Long id);

    PageResult<MeetingBookingDO> getMeetingBookingPage(MeetingBookingPageReqVO pageReqVO);

    PageResult<MeetingBookingDO> getMyMeetingBookingPage(Long applicantUserId, MeetingBookingPageReqVO pageReqVO);

    List<MeetingBookingDO> getWeekScheduleList(MeetingBookingScheduleReqVO reqVO);

    List<MeetingBookingDO> getMonthScheduleList(MeetingBookingScheduleReqVO reqVO);

    List<MeetingBookingDO> checkConflictList(MeetingBookingConflictCheckReqVO reqVO);

    List<Long> getAttendeeUserIds(Long bookingId);

    Map<Long, List<Long>> getAttendeeUserIdsMap(List<Long> bookingIds);

    List<MeetingBookingDO> getMyCalendarList(Long applicantUserId, LocalDateTime startTime, LocalDateTime endTime);

}
