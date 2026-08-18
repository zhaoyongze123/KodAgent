package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAStaffingRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAStaffingDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAStaffingService;
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

@Tag(name = "管理后台 - OA 项目人员调配申请")
@RestController
@RequestMapping("/bpm/oa/staffing")
@Validated
public class BpmOAStaffingController {

    @Resource
    private BpmOAStaffingService staffingService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建项目人员调配申请")
    public CommonResult<Long> createStaffing(@Valid @RequestBody BpmOAStaffingCreateReqVO createReqVO) {
        return success(staffingService.createStaffing(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得项目人员调配申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAStaffingRespVO> getStaffing(@RequestParam("id") Long id) {
        BpmOAStaffingDO staffing = staffingService.getStaffing(id);
        return success(BeanUtils.toBean(staffing, BpmOAStaffingRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得项目人员调配申请分页")
    public CommonResult<PageResult<BpmOAStaffingRespVO>> getStaffingPage(@Valid BpmOAStaffingPageReqVO pageVO) {
        PageResult<BpmOAStaffingDO> pageResult = staffingService.getStaffingPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAStaffingRespVO.class));
    }

}
