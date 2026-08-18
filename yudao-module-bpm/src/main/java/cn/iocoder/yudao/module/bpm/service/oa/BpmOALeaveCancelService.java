package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveCancelDO;

import javax.validation.Valid;

public interface BpmOALeaveCancelService {

    Long createLeaveCancel(Long userId, @Valid BpmOALeaveCancelCreateReqVO createReqVO);

    void updateLeaveCancelStatus(Long id, Integer status);

    BpmOALeaveCancelDO getLeaveCancel(Long id);

    PageResult<BpmOALeaveCancelDO> getLeaveCancelPage(Long userId, BpmOALeaveCancelPageReqVO pageReqVO);

}
