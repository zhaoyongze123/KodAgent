package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOutingRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOutingDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOutingService;
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

@Tag(name = "管理后台 - OA 临时外出申请")
@RestController
@RequestMapping("/bpm/oa/outing")
@Validated
public class BpmOAOutingController {

    @Resource
    private BpmOAOutingService outingService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建临时外出申请")
    public CommonResult<Long> createOuting(@Valid @RequestBody BpmOAOutingCreateReqVO createReqVO) {
        return success(outingService.createOuting(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得临时外出申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAOutingRespVO> getOuting(@RequestParam("id") Long id) {
        BpmOAOutingDO outing = outingService.getOuting(id);
        return success(BeanUtils.toBean(outing, BpmOAOutingRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得临时外出申请分页")
    public CommonResult<PageResult<BpmOAOutingRespVO>> getOutingPage(@Valid BpmOAOutingPageReqVO pageVO) {
        PageResult<BpmOAOutingDO> pageResult = outingService.getOutingPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAOutingRespVO.class));
    }

}
