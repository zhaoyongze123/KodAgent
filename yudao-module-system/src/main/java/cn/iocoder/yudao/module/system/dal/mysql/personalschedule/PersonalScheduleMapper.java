package cn.iocoder.yudao.module.system.dal.mysql.personalschedule;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import org.apache.ibatis.annotations.Mapper;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface PersonalScheduleMapper extends BaseMapperX<PersonalScheduleDO> {

    default List<PersonalScheduleDO> selectMyCalendarList(Long ownerUserId, LocalDateTime startTime, LocalDateTime endTime) {
        return selectList(new LambdaQueryWrapperX<PersonalScheduleDO>()
                .eq(PersonalScheduleDO::getOwnerUserId, ownerUserId)
                .lt(PersonalScheduleDO::getStartTime, endTime)
                .gt(PersonalScheduleDO::getEndTime, startTime)
                .orderByAsc(PersonalScheduleDO::getStartTime)
                .orderByAsc(PersonalScheduleDO::getId));
    }

}
