package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimeCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAOvertimeRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAOvertimeDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAOvertimeService;
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

/**
 * OA 加班申请 Controller，用于演示自己存储数据，接入工作流的例子
 *
 * @author jason
 * @author 芋道源码
 */
@Tag(name = "管理后台 - OA 加班申请")
@RestController
@RequestMapping("/bpm/oa/overtime")
@Validated
public class BpmOAOvertimeController {

    @Resource
    private BpmOAOvertimeService overtimeService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建请求申请")
    public CommonResult<Long> createOvertime(@Valid @RequestBody BpmOAOvertimeCreateReqVO createReqVO) {
        return success(overtimeService.createOvertime(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得加班申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAOvertimeRespVO> getOvertime(@RequestParam("id") Long id) {
        BpmOAOvertimeDO overtime = overtimeService.getOvertime(id);
        return success(BeanUtils.toBean(overtime, BpmOAOvertimeRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得加班申请分页")
    public CommonResult<PageResult<BpmOAOvertimeRespVO>> getOvertimePage(@Valid BpmOAOvertimePageReqVO pageVO) {
        PageResult<BpmOAOvertimeDO> pageResult = overtimeService.getOvertimePage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAOvertimeRespVO.class));
    }

}
