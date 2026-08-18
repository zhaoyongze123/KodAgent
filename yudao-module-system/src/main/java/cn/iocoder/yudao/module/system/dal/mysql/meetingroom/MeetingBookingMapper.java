package cn.iocoder.yudao.module.system.dal.mysql.meetingroom;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking.MeetingBookingScheduleReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingDO;
import org.apache.ibatis.annotations.Mapper;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;

@Mapper
public interface MeetingBookingMapper extends BaseMapperX<MeetingBookingDO> {

    default PageResult<MeetingBookingDO> selectPage(MeetingBookingPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<MeetingBookingDO>()
                .eqIfPresent(MeetingBookingDO::getApplicantUserId, reqVO.getApplicantUserId())
                .eqIfPresent(MeetingBookingDO::getMeetingRoomId, reqVO.getMeetingRoomId())
                .likeIfPresent(MeetingBookingDO::getSubject, reqVO.getSubject())
                .eqIfPresent(MeetingBookingDO::getStatus, reqVO.getStatus())
                .geIfPresent(MeetingBookingDO::getStartTime, reqVO.getStartTimeFrom())
                .leIfPresent(MeetingBookingDO::getStartTime, reqVO.getStartTimeTo())
                .orderByDesc(MeetingBookingDO::getStartTime)
                .orderByDesc(MeetingBookingDO::getId));
    }

    default PageResult<MeetingBookingDO> selectMyPage(Long applicantUserId, MeetingBookingPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<MeetingBookingDO>()
                .eq(MeetingBookingDO::getApplicantUserId, applicantUserId)
                .eqIfPresent(MeetingBookingDO::getMeetingRoomId, reqVO.getMeetingRoomId())
                .likeIfPresent(MeetingBookingDO::getSubject, reqVO.getSubject())
                .eqIfPresent(MeetingBookingDO::getStatus, reqVO.getStatus())
                .geIfPresent(MeetingBookingDO::getStartTime, reqVO.getStartTimeFrom())
                .leIfPresent(MeetingBookingDO::getStartTime, reqVO.getStartTimeTo())
                .orderByDesc(MeetingBookingDO::getStartTime)
                .orderByDesc(MeetingBookingDO::getId));
    }

    default List<MeetingBookingDO> selectScheduleList(MeetingBookingScheduleReqVO reqVO) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingDO>()
                .eqIfPresent(MeetingBookingDO::getMeetingRoomId, reqVO.getMeetingRoomId())
                .eqIfPresent(MeetingBookingDO::getApplicantUserId, reqVO.getApplicantUserId())
                .likeIfPresent(MeetingBookingDO::getSubject, reqVO.getSubject())
                .geIfPresent(MeetingBookingDO::getStartTime, reqVO.getStartTime())
                .ltIfPresent(MeetingBookingDO::getStartTime, reqVO.getEndTime())
                .orderByAsc(MeetingBookingDO::getStartTime)
                .orderByAsc(MeetingBookingDO::getMeetingRoomId)
                .orderByAsc(MeetingBookingDO::getId));
    }

    default List<MeetingBookingDO> selectMyCalendarList(Long applicantUserId, LocalDateTime startTime, LocalDateTime endTime) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingDO>()
                .eq(MeetingBookingDO::getApplicantUserId, applicantUserId)
                .eq(MeetingBookingDO::getStatus, 1)
                .lt(MeetingBookingDO::getStartTime, endTime)
                .gt(MeetingBookingDO::getEndTime, startTime)
                .orderByAsc(MeetingBookingDO::getStartTime)
                .orderByAsc(MeetingBookingDO::getId));
    }

    default List<MeetingBookingDO> selectCalendarListByIds(Collection<Long> bookingIds, LocalDateTime startTime,
                                                           LocalDateTime endTime) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingDO>()
                .inIfPresent(MeetingBookingDO::getId, bookingIds)
                .eq(MeetingBookingDO::getStatus, 1)
                .lt(MeetingBookingDO::getStartTime, endTime)
                .gt(MeetingBookingDO::getEndTime, startTime)
                .orderByAsc(MeetingBookingDO::getStartTime)
                .orderByAsc(MeetingBookingDO::getId));
    }

    default List<MeetingBookingDO> selectConflictList(Long roomId, LocalDateTime startTime, LocalDateTime endTime,
                                                      Long excludeId) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingDO>()
                .eq(MeetingBookingDO::getMeetingRoomId, roomId)
                .eq(MeetingBookingDO::getStatus, 1)
                .neIfPresent(MeetingBookingDO::getId, excludeId)
                .lt(MeetingBookingDO::getStartTime, endTime)
                .gt(MeetingBookingDO::getEndTime, startTime)
                .orderByAsc(MeetingBookingDO::getStartTime));
    }

}
