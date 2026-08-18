package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAStaffingDO;

import javax.validation.Valid;

public interface BpmOAStaffingService {

    Long createStaffing(Long userId, @Valid BpmOAStaffingCreateReqVO createReqVO);

    void updateStaffingStatus(Long id, Integer status);

    BpmOAStaffingDO getStaffing(Long id);

    PageResult<BpmOAStaffingDO> getStaffingPage(Long userId, BpmOAStaffingPageReqVO pageReqVO);

}
