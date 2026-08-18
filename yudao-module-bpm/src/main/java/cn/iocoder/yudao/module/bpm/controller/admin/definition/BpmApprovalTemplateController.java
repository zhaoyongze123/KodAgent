package cn.iocoder.yudao.module.bpm.controller.admin.definition;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.process.BpmProcessDefinitionRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplatePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateUpdateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateUpdateVisibleReqVO;
import cn.iocoder.yudao.module.bpm.service.definition.BpmApprovalTemplateService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - BPM 审批模板")
@RestController
@RequestMapping("/bpm/approval-template")
@Validated
public class BpmApprovalTemplateController {

    @Resource
    private BpmApprovalTemplateService approvalTemplateService;

    @GetMapping("/page")
    @Operation(summary = "获得审批模板分页")
    @PreAuthorize("@ss.hasPermission('bpm:process-definition:query')")
    public CommonResult<PageResult<BpmApprovalTemplateRespVO>> getApprovalTemplatePage(
            @Valid BpmApprovalTemplatePageReqVO pageReqVO) {
        return success(approvalTemplateService.getApprovalTemplatePage(pageReqVO));
    }

    @GetMapping("/get")
    @Operation(summary = "获得审批模板详情")
    @Parameter(name = "id", description = "模板编号", required = true, example = "1")
    @PreAuthorize("@ss.hasPermission('bpm:process-definition:query')")
    public CommonResult<BpmApprovalTemplateRespVO> getApprovalTemplate(@RequestParam("id") Long id) {
        return success(approvalTemplateService.getApprovalTemplate(id));
    }

    @PutMapping("/update")
    @Operation(summary = "更新审批模板")
    @PreAuthorize("@ss.hasPermission('bpm:model:update')")
    public CommonResult<Boolean> updateApprovalTemplate(@Valid @RequestBody BpmApprovalTemplateUpdateReqVO reqVO) {
        approvalTemplateService.updateApprovalTemplate(reqVO);
        return success(true);
    }

    @PutMapping("/update-visible")
    @Operation(summary = "更新审批模板上下架")
    @PreAuthorize("@ss.hasPermission('bpm:model:update')")
    public CommonResult<Boolean> updateApprovalTemplateVisible(@Valid @RequestBody BpmApprovalTemplateUpdateVisibleReqVO reqVO) {
        approvalTemplateService.updateApprovalTemplateVisible(reqVO.getId(), reqVO.getVisible());
        return success(true);
    }

    @GetMapping("/list")
    @Operation(summary = "获得当前用户可发起的审批模板列表")
    public CommonResult<List<BpmProcessDefinitionRespVO>> getApprovalTemplateList() {
        return success(approvalTemplateService.getApprovalTemplateList(getLoginUserId()));
    }

}
