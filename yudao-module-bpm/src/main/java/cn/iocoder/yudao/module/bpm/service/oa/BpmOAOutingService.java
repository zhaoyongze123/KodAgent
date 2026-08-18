package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOutingDO;

import javax.validation.Valid;

public interface BpmOAOutingService {

    Long createOuting(Long userId, @Valid BpmOAOutingCreateReqVO createReqVO);

    void updateOutingStatus(Long id, Integer status);

    BpmOAOutingDO getOuting(Long id);

    PageResult<BpmOAOutingDO> getOutingPage(Long userId, BpmOAOutingPageReqVO pageReqVO);

}
