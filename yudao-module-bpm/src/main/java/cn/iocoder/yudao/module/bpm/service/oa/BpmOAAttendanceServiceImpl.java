package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendanceCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendancePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAAttendanceDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAAttendanceMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_LEAVE_NOT_EXISTS;

/**
 * OA 补卡申请 Service 实现类
 *
 * @author jason
 * @author 芋道源码
 */
@Service
@Validated
public class BpmOAAttendanceServiceImpl implements BpmOAAttendanceService {

    /**
     * OA 补卡对应的流程定义 KEY
     */
    public static final String PROCESS_KEY = "oa_attendance";

    @Resource
    private BpmOAAttendanceMapper attendanceMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createAttendance(Long userId, BpmOAAttendanceCreateReqVO createReqVO) {
        // 插入 OA 补卡单
        long day = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toDays();
        BpmOAAttendanceDO attendance = BeanUtils.toBean(createReqVO, BpmOAAttendanceDO.class)
                .setUserId(userId).setDay(day).setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        attendanceMapper.insert(attendance);

        // 发起 BPM 流程
        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(attendance.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        // 将工作流的编号，更新到 OA 补卡单中
        attendanceMapper.updateById(new BpmOAAttendanceDO().setId(attendance.getId()).setProcessInstanceId(processInstanceId));
        return attendance.getId();
    }

    @Override
    public void updateAttendanceStatus(Long id, Integer status) {
        validateAttendanceExists(id);
        attendanceMapper.updateById(new BpmOAAttendanceDO().setId(id).setStatus(status));
    }

    private void validateAttendanceExists(Long id) {
        if (attendanceMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

    @Override
    public BpmOAAttendanceDO getAttendance(Long id) {
        return attendanceMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAAttendanceDO> getAttendancePage(Long userId, BpmOAAttendancePageReqVO pageReqVO) {
        return attendanceMapper.selectPage(userId, pageReqVO);
    }

}
