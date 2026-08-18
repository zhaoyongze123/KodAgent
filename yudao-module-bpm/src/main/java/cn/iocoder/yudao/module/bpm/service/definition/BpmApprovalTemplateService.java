package cn.iocoder.yudao.module.bpm.service.definition;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.process.BpmProcessDefinitionRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplatePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateUpdateReqVO;

import java.util.List;

/**
 * BPM 审批模板 Service 接口
 *
 * @author Codex
 */
public interface BpmApprovalTemplateService {

    /**
     * 获得审批模板分页
     *
     * @param pageReqVO 分页参数
     * @return 审批模板分页
     */
    PageResult<BpmApprovalTemplateRespVO> getApprovalTemplatePage(BpmApprovalTemplatePageReqVO pageReqVO);

    /**
     * 获得审批模板详情
     *
     * @param id 模板编号
     * @return 审批模板
     */
    BpmApprovalTemplateRespVO getApprovalTemplate(Long id);

    /**
     * 更新审批模板
     *
     * @param reqVO 更新参数
     */
    void updateApprovalTemplate(BpmApprovalTemplateUpdateReqVO reqVO);

    /**
     * 修改审批模板上下架
     *
     * @param id 模板编号
     * @param visible 是否上架
     */
    void updateApprovalTemplateVisible(Long id, Boolean visible);

    /**
     * 获得可发起的审批模板列表
     *
     * @param userId 当前用户
     * @return 模板列表
     */
    List<BpmProcessDefinitionRespVO> getApprovalTemplateList(Long userId);

}
