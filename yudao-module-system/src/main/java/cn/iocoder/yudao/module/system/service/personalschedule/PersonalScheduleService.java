package cn.iocoder.yudao.module.system.service.personalschedule;

import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;

import javax.validation.Valid;
import java.util.List;
import java.util.Map;

public interface PersonalScheduleService {

    Long createPersonalSchedule(Long ownerUserId, @Valid PersonalScheduleSaveReqVO createReqVO);

    void updatePersonalSchedule(Long ownerUserId, @Valid PersonalScheduleSaveReqVO updateReqVO);

    void deletePersonalSchedule(Long ownerUserId, Long id);

    PersonalScheduleDO getPersonalSchedule(Long ownerUserId, Long id);

    List<PersonalScheduleDO> getMyCalendarList(Long ownerUserId, @Valid PersonalScheduleCalendarReqVO reqVO);

    List<Long> getAttendeeUserIds(Long scheduleId);

    Map<Long, List<Long>> getAttendeeUserIdsMap(List<Long> scheduleIds);

}
