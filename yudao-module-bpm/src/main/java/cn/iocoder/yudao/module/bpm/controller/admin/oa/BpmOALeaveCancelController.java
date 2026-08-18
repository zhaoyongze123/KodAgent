package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOALeaveCancelRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOALeaveCancelDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOALeaveCancelService;
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

@Tag(name = "管理后台 - OA 销假申请")
@RestController
@RequestMapping("/bpm/oa/leave-cancel")
@Validated
public class BpmOALeaveCancelController {

    @Resource
    private BpmOALeaveCancelService leaveCancelService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建销假申请")
    public CommonResult<Long> createLeaveCancel(@Valid @RequestBody BpmOALeaveCancelCreateReqVO createReqVO) {
        return success(leaveCancelService.createLeaveCancel(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得销假申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOALeaveCancelRespVO> getLeaveCancel(@RequestParam("id") Long id) {
        BpmOALeaveCancelDO leaveCancel = leaveCancelService.getLeaveCancel(id);
        return success(BeanUtils.toBean(leaveCancel, BpmOALeaveCancelRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得销假申请分页")
    public CommonResult<PageResult<BpmOALeaveCancelRespVO>> getLeaveCancelPage(@Valid BpmOALeaveCancelPageReqVO pageVO) {
        PageResult<BpmOALeaveCancelDO> pageResult = leaveCancelService.getLeaveCancelPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOALeaveCancelRespVO.class));
    }

}
