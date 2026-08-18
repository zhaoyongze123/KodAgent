package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOADocumentDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOADocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - OA 合同/文件审批")
@RestController
@RequestMapping("/bpm/oa/document")
@Validated
public class BpmOADocumentController {

    @Resource
    private BpmOADocumentService documentService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建合同/文件审批")
    public CommonResult<Long> createDocument(@Valid @RequestBody BpmOADocumentCreateReqVO createReqVO) {
        return success(documentService.createDocument(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得合同/文件审批")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOADocumentRespVO> getDocument(@RequestParam("id") Long id) {
        BpmOADocumentDO document = documentService.getDocument(id);
        return success(BeanUtils.toBean(document, BpmOADocumentRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得合同/文件审批分页")
    public CommonResult<PageResult<BpmOADocumentRespVO>> getDocumentPage(@Valid BpmOADocumentPageReqVO pageVO) {
        PageResult<BpmOADocumentDO> pageResult = documentService.getDocumentPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOADocumentRespVO.class));
    }

}
