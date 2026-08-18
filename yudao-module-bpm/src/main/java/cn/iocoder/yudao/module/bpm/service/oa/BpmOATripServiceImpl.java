package cn.iocoder.yudao.module.bpm.service.oa;

import cn.hutool.core.date.LocalDateTimeUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOATripDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOATripMapper;
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
 * OA 出差申请 Service 实现类
 *
 * @author jason
 * @author 芋道源码
 */
@Service
@Validated
public class BpmOATripServiceImpl implements BpmOATripService {

    /**
     * OA 出差对应的流程定义 KEY
     */
    public static final String PROCESS_KEY = "oa_trip";

    @Resource
    private BpmOATripMapper tripMapper;

    @Resource
    private BpmProcessInstanceApi processInstanceApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createTrip(Long userId, BpmOATripCreateReqVO createReqVO) {
        // 插入 OA 出差单
        long day = LocalDateTimeUtil.between(createReqVO.getStartTime(), createReqVO.getEndTime()).toDays();
        BpmOATripDO trip = BeanUtils.toBean(createReqVO, BpmOATripDO.class)
                .setUserId(userId).setDay(day).setStatus(BpmTaskStatusEnum.RUNNING.getStatus());
        tripMapper.insert(trip);

        // 发起 BPM 流程
        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("day", day);
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(trip.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));

        // 将工作流的编号，更新到 OA 出差单中
        tripMapper.updateById(new BpmOATripDO().setId(trip.getId()).setProcessInstanceId(processInstanceId));
        return trip.getId();
    }

    @Override
    public void updateTripStatus(Long id, Integer status) {
        validateTripExists(id);
        tripMapper.updateById(new BpmOATripDO().setId(id).setStatus(status));
    }

    private void validateTripExists(Long id) {
        if (tripMapper.selectById(id) == null) {
            throw exception(OA_LEAVE_NOT_EXISTS);
        }
    }

    @Override
    public BpmOATripDO getTrip(Long id) {
        return tripMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOATripDO> getTripPage(Long userId, BpmOATripPageReqVO pageReqVO) {
        return tripMapper.selectPage(userId, pageReqVO);
    }

}
