package cn.iocoder.yudao.module.system.dal.mysql.meetingroom;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.meetingroom.MeetingBookingAttendeeDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface MeetingBookingAttendeeMapper extends BaseMapperX<MeetingBookingAttendeeDO> {

    default List<MeetingBookingAttendeeDO> selectListByBookingId(Long bookingId) {
        return selectList(MeetingBookingAttendeeDO::getBookingId, bookingId);
    }

    default List<MeetingBookingAttendeeDO> selectListByBookingIds(List<Long> bookingIds) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingAttendeeDO>()
                .inIfPresent(MeetingBookingAttendeeDO::getBookingId, bookingIds));
    }

    default List<MeetingBookingAttendeeDO> selectListByUserId(Long userId) {
        return selectList(new LambdaQueryWrapperX<MeetingBookingAttendeeDO>()
                .eq(MeetingBookingAttendeeDO::getUserId, userId));
    }

    default void deleteByBookingId(Long bookingId) {
        delete(new LambdaQueryWrapperX<MeetingBookingAttendeeDO>()
                .eq(MeetingBookingAttendeeDO::getBookingId, bookingId));
    }

}
