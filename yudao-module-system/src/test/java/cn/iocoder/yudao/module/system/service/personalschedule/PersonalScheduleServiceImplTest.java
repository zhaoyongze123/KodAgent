package cn.iocoder.yudao.module.system.service.personalschedule;

import cn.iocoder.yudao.framework.test.core.ut.BaseDbUnitTest;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleCalendarReqVO;
import cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo.PersonalScheduleSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.dal.mysql.personalschedule.PersonalScheduleMapper;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Import;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.List;

import static cn.iocoder.yudao.framework.test.core.util.AssertUtils.assertServiceException;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PERSONAL_SCHEDULE_NOT_OWNER;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PERSONAL_SCHEDULE_TIME_INVALID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Import(PersonalScheduleServiceImpl.class)
class PersonalScheduleServiceImplTest extends BaseDbUnitTest {

    @Resource
    private PersonalScheduleService personalScheduleService;
    @Resource
    private PersonalScheduleMapper personalScheduleMapper;

    @Test
    void testCreatePersonalSchedule_success() {
        LocalDateTime startTime = LocalDateTime.now().plusDays(1).withHour(9).withMinute(0).withSecond(0).withNano(0);
        PersonalScheduleSaveReqVO reqVO = createReqVO(startTime);

        Long scheduleId = personalScheduleService.createPersonalSchedule(100L, reqVO);

        PersonalScheduleDO schedule = personalScheduleMapper.selectById(scheduleId);
        assertNotNull(schedule);
        assertEquals(100L, schedule.getOwnerUserId());
        assertEquals("外出调研", schedule.getTitle());
    }

    @Test
    void testCreatePersonalSchedule_timeInvalid() {
        LocalDateTime startTime = LocalDateTime.now().plusDays(1).withHour(14).withMinute(0).withSecond(0).withNano(0);
        PersonalScheduleSaveReqVO reqVO = createReqVO(startTime);
        reqVO.setEndTime(startTime.minusHours(1));

        assertServiceException(() -> personalScheduleService.createPersonalSchedule(100L, reqVO),
                PERSONAL_SCHEDULE_TIME_INVALID);
    }

    @Test
    void testUpdatePersonalSchedule_notOwner() {
        LocalDateTime startTime = LocalDateTime.now().plusDays(1).withHour(10).withMinute(0).withSecond(0).withNano(0);
        Long scheduleId = personalScheduleService.createPersonalSchedule(200L, createReqVO(startTime));
        PersonalScheduleSaveReqVO reqVO = createReqVO(startTime.plusHours(2));
        reqVO.setId(scheduleId);

        assertServiceException(() -> personalScheduleService.updatePersonalSchedule(100L, reqVO),
                PERSONAL_SCHEDULE_NOT_OWNER);
    }

    @Test
    void testGetMyCalendarList_success() {
        LocalDateTime startTime = LocalDateTime.now().plusDays(2).withHour(13).withMinute(0).withSecond(0).withNano(0);
        personalScheduleService.createPersonalSchedule(100L, createReqVO(startTime));

        PersonalScheduleCalendarReqVO reqVO = new PersonalScheduleCalendarReqVO();
        reqVO.setStartTime(startTime.minusHours(1));
        reqVO.setEndTime(startTime.plusHours(3));
        List<PersonalScheduleDO> result = personalScheduleService.getMyCalendarList(100L, reqVO);

        assertEquals(1, result.size());
        assertEquals("外出调研", result.get(0).getTitle());
    }

    private PersonalScheduleSaveReqVO createReqVO(LocalDateTime startTime) {
        return new PersonalScheduleSaveReqVO()
                .setTitle("外出调研")
                .setStartTime(startTime)
                .setEndTime(startTime.plusHours(2))
                .setLocation("客户现场")
                .setDescription("沟通项目需求")
                .setAttendeeUserIds(List.of(11L, 12L))
                .setOtherParticipants("客户张三");
    }

}
