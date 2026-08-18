package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimeCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOvertimeDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAOvertimeMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_LEAVE_NOT_EXISTS;

/**
 * OA 加班申请 Service 实现类
 *
 * @author jason
 * @author 芋道源码
 */
@Service
@Validated
public class BpmOAOvertimeServiceImpl implements BpmOAOvertimeService {

    /**
     * OA 加班对应的流程定义 KEY
     */
    public static final String PROCESS_KEY = "oa_overtime";

    @Resource
    private BpmOAOvertimeMapper overtimeMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createOvertime(Long userId, BpmOAOvertimeCreateReqVO createReqVO) {
        // 插入 OA 加班单
        BigDecimal durationHours = calculateDurationHours(createReqVO);
        long day = durationHours.divide(new BigDecimal("8"), 0, RoundingMode.UP).longValue();
        BpmOAOvertimeDO overtime = BeanUtils.toBean(createReqVO, BpmOAOvertimeDO.class)
                .setUserId(userId)
                .setDay(day)
                .setDurationHours(durationHours)
                .setWorkDate(createReqVO.getWorkDate() != null ? createReqVO.getWorkDate() : createReqVO.getStartTime().toLocalDate())
                .setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        overtimeMapper.insert(overtime);

        // 发起 BPM 流程
        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        processInstanceVariables.put("durationHours", durationHours);
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(overtime.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        // 将工作流的编号，更新到 OA 加班单中
        overtimeMapper.updateById(new BpmOAOvertimeDO().setId(overtime.getId()).setProcessInstanceId(processInstanceId));
        return overtime.getId();
    }

    @Override
    public void updateOvertimeStatus(Long id, Integer status) {
        validateOvertimeExists(id);
        overtimeMapper.updateById(new BpmOAOvertimeDO().setId(id).setStatus(status));
    }

    private void validateOvertimeExists(Long id) {
        if (overtimeMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

    @Override
    public BpmOAOvertimeDO getOvertime(Long id) {
        return overtimeMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAOvertimeDO> getOvertimePage(Long userId, BpmOAOvertimePageReqVO pageReqVO) {
        return overtimeMapper.selectPage(userId, pageReqVO);
    }

    private BigDecimal calculateDurationHours(BpmOAOvertimeCreateReqVO createReqVO) {
        if (createReqVO.getDurationHours() != null) {
            return createReqVO.getDurationHours();
        }
        long minutes = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toMinutes();
        return BigDecimal.valueOf(minutes)
                .divide(new BigDecimal("60"), 2, RoundingMode.HALF_UP);
    }

}
