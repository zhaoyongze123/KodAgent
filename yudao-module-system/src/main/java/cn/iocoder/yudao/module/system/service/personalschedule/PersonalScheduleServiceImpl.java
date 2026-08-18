package cn.iocoder.yudao.module.system.service.personalschedule;

import cn.hutool.core.collection.CollUtil;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleAttendeeDO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.dal.mysql.personalschedule.PersonalScheduleAttendeeMapper;
import cn.iocoder.yudao.module.system.dal.mysql.personalschedule.PersonalScheduleMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Validated
public class PersonalScheduleServiceImpl implements PersonalScheduleService {

    @Resource
    private PersonalScheduleMapper personalScheduleMapper;
    @Resource
    private PersonalScheduleAttendeeMapper personalScheduleAttendeeMapper;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createPersonalSchedule(Long ownerUserId, PersonalScheduleSaveReqVO createReqVO) {
        validateTimeRange(createReqVO.getStartTime(), createReqVO.getEndTime());
        PersonalScheduleDO schedule = BeanUtils.toBean(createReqVO, PersonalScheduleDO.class);
        schedule.setOwnerUserId(ownerUserId);
        personalScheduleMapper.insert(schedule);
        saveAttendees(schedule.getId(), createReqVO.getAttendeeUserIds());
        return schedule.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updatePersonalSchedule(Long ownerUserId, PersonalScheduleSaveReqVO updateReqVO) {
        validateTimeRange(updateReqVO.getStartTime(), updateReqVO.getEndTime());
        PersonalScheduleDO existed = validateOwnerSchedule(ownerUserId, updateReqVO.getId());
        PersonalScheduleDO updateObj = BeanUtils.toBean(updateReqVO, PersonalScheduleDO.class);
        updateObj.setOwnerUserId(existed.getOwnerUserId());
        personalScheduleMapper.updateById(updateObj);
        saveAttendees(updateReqVO.getId(), updateReqVO.getAttendeeUserIds());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deletePersonalSchedule(Long ownerUserId, Long id) {
        validateOwnerSchedule(ownerUserId, id);
        personalScheduleAttendeeMapper.deleteByScheduleId(id);
        personalScheduleMapper.deleteById(id);
    }

    @Override
    public PersonalScheduleDO getPersonalSchedule(Long ownerUserId, Long id) {
        return validateOwnerSchedule(ownerUserId, id);
    }

    @Override
    public List<PersonalScheduleDO> getMyCalendarList(Long ownerUserId, PersonalScheduleCalendarReqVO reqVO) {
        validateTimeRange(reqVO.getStartTime(), reqVO.getEndTime());
        return personalScheduleMapper.selectMyCalendarList(ownerUserId, reqVO.getStartTime(), reqVO.getEndTime());
    }

    @Override
    public List<Long> getAttendeeUserIds(Long scheduleId) {
        return personalScheduleAttendeeMapper.selectListByScheduleId(scheduleId).stream()
                .map(PersonalScheduleAttendeeDO::getUserId)
                .collect(Collectors.toList());
    }

    @Override
    public Map<Long, List<Long>> getAttendeeUserIdsMap(List<Long> scheduleIds) {
        if (CollUtil.isEmpty(scheduleIds)) {
            return Collections.emptyMap();
        }
        return personalScheduleAttendeeMapper.selectListByScheduleIds(scheduleIds).stream()
                .collect(Collectors.groupingBy(PersonalScheduleAttendeeDO::getScheduleId,
                        LinkedHashMap::new,
                        Collectors.mapping(PersonalScheduleAttendeeDO::getUserId, Collectors.toList())));
    }

    private PersonalScheduleDO validateOwnerSchedule(Long ownerUserId, Long id) {
        PersonalScheduleDO schedule = personalScheduleMapper.selectById(id);
        if (schedule == null) {
            throw exception(PERSONAL_SCHEDULE_NOT_EXISTS);
        }
        if (!Objects.equals(schedule.getOwnerUserId(), ownerUserId)) {
            throw exception(PERSONAL_SCHEDULE_NOT_OWNER);
        }
        return schedule;
    }

    private void validateTimeRange(LocalDateTime startTime, LocalDateTime endTime) {
        if (startTime == null || endTime == null || !startTime.isBefore(endTime)) {
            throw exception(PERSONAL_SCHEDULE_TIME_INVALID);
        }
    }

    private void saveAttendees(Long scheduleId, List<Long> attendeeUserIds) {
        personalScheduleAttendeeMapper.deleteByScheduleId(scheduleId);
        if (CollUtil.isEmpty(attendeeUserIds)) {
            return;
        }
        attendeeUserIds.stream()
                .filter(Objects::nonNull)
                .distinct()
                .forEach(userId -> {
                    PersonalScheduleAttendeeDO attendee = new PersonalScheduleAttendeeDO();
                    attendee.setScheduleId(scheduleId);
                    attendee.setUserId(userId);
                    personalScheduleAttendeeMapper.insert(attendee);
                });
    }

}
