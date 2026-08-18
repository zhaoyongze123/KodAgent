package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveCancelDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOALeaveCancelMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_LEAVE_NOT_EXISTS;

@Service
@Validated
public class BpmOALeaveCancelServiceImpl implements BpmOALeaveCancelService {

    public static final String PROCESS_KEY = "oa_leave_cancel";

    @Resource
    private BpmOALeaveCancelMapper leaveCancelMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createLeaveCancel(Long userId, BpmOALeaveCancelCreateReqVO createReqVO) {
        long day = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toDays();
        BpmOALeaveCancelDO leaveCancel = BeanUtils.toBean(createReqVO, BpmOALeaveCancelDO.class)
                .setUserId(userId).setDay(day).setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        leaveCancelMapper.insert(leaveCancel);

        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(leaveCancel.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        leaveCancelMapper.updateById(new BpmOALeaveCancelDO().setId(leaveCancel.getId()).setProcessInstanceId(processInstanceId));
        return leaveCancel.getId();
    }

    @Override
    public void updateLeaveCancelStatus(Long id, Integer status) {
        validateLeaveCancelExists(id);
        leaveCancelMapper.updateById(new BpmOALeaveCancelDO().setId(id).setStatus(status));
    }

    @Override
    public BpmOALeaveCancelDO getLeaveCancel(Long id) {
        return leaveCancelMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOALeaveCancelDO> getLeaveCancelPage(Long userId, BpmOALeaveCancelPageReqVO pageReqVO) {
        return leaveCancelMapper.selectPage(userId, pageReqVO);
    }

    private void validateLeaveCancelExists(Long id) {
        if (leaveCancelMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

}
