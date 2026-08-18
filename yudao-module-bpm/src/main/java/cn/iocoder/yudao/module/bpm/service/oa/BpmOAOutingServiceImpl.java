package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOutingDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOAOutingMapper;
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

@Service
@Validated
public class BpmOAOutingServiceImpl implements BpmOAOutingService {

    public static final String PROCESS_KEY = "oa_outing";

    @Resource
    private BpmOAOutingMapper outingMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createOuting(Long userId, BpmOAOutingCreateReqVO createReqVO) {
        BigDecimal durationHours = calculateDurationHours(createReqVO);
        BpmOAOutingDO outing = BeanUtils.toBean(createReqVO, BpmOAOutingDO.class)
                .setUserId(userId)
                .setDurationHours(durationHours)
                .setOutsideOffice(Boolean.TRUE.equals(createReqVO.getOutsideOffice()))
                .setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        outingMapper.insert(outing);

        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("durationHours", durationHours);
        processInstanceVariables.put("day", durationHours.divide(new BigDecimal("8"), 2, RoundingMode.HALF_UP));
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(outing.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        outingMapper.updateById(new BpmOAOutingDO().setId(outing.getId()).setProcessInstanceId(processInstanceId));
        return outing.getId();
    }

    @Override
    public void updateOutingStatus(Long id, Integer status) {
        validateOutingExists(id);
        outingMapper.updateById(new BpmOAOutingDO().setId(id).setStatus(status));
    }

    @Override
    public BpmOAOutingDO getOuting(Long id) {
        return outingMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOAOutingDO> getOutingPage(Long userId, BpmOAOutingPageReqVO pageReqVO) {
        return outingMapper.selectPage(userId, pageReqVO);
    }

    private void validateOutingExists(Long id) {
        if (outingMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

    private BigDecimal calculateDurationHours(BpmOAOutingCreateReqVO createReqVO) {
        if (createReqVO.getDurationHours() != null) {
            return createReqVO.getDurationHours();
        }
        long minutes = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toMinutes();
        return BigDecimal.valueOf(minutes)
                .divide(new BigDecimal("60"), 2, RoundingMode.HALF_UP);
    }

}
