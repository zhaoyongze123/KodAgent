package cn.iocoder.yudao.module.system.dal.mysql.personalschedule;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleAttendeeDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface PersonalScheduleAttendeeMapper extends BaseMapperX<PersonalScheduleAttendeeDO> {

    default List<PersonalScheduleAttendeeDO> selectListByScheduleId(Long scheduleId) {
        return selectList(PersonalScheduleAttendeeDO::getScheduleId, scheduleId);
    }

    default List<PersonalScheduleAttendeeDO> selectListByScheduleIds(List<Long> scheduleIds) {
        return selectList(new LambdaQueryWrapperX<PersonalScheduleAttendeeDO>()
                .inIfPresent(PersonalScheduleAttendeeDO::getScheduleId, scheduleIds));
    }

    default void deleteByScheduleId(Long scheduleId) {
        delete(new LambdaQueryWrapperX<PersonalScheduleAttendeeDO>()
                .eq(PersonalScheduleAttendeeDO::getScheduleId, scheduleId));
    }

}
