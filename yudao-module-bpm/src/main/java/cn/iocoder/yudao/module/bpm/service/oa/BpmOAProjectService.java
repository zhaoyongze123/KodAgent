package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAProjectDO;

import javax.validation.Valid;

public interface BpmOAProjectService {

    Long createProject(Long userId, @Valid BpmOAProjectCreateReqVO createReqVO);

    void updateProjectStatus(Long id, Integer status);

    BpmOAProjectDO getProject(Long id);

    PageResult<BpmOAProjectDO> getProjectPage(Long userId, BpmOAProjectPageReqVO pageReqVO);

}
