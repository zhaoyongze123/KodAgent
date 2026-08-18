package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOADocumentDO;

import javax.validation.Valid;

public interface BpmOADocumentService {

    Long createDocument(Long userId, @Valid BpmOADocumentCreateReqVO createReqVO);

    void updateDocumentStatus(Long id, Integer status);

    BpmOADocumentDO getDocument(Long id);

    PageResult<BpmOADocumentDO> getDocumentPage(Long userId, BpmOADocumentPageReqVO pageReqVO);

}
