package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOATripRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOATripDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOATripService;
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
 * OA 出差申请 Controller，用于演示自己存储数据，接入工作流的例子
 *
 * @author jason
 * @author 芋道源码
 */
@Tag(name = "管理后台 - OA 出差申请")
@RestController
@RequestMapping("/bpm/oa/trip")
@Validated
public class BpmOATripController {

    @Resource
    private BpmOATripService tripService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建请求申请")
    public CommonResult<Long> createTrip(@Valid @RequestBody BpmOATripCreateReqVO createReqVO) {
        return success(tripService.createTrip(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得出差申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOATripRespVO> getTrip(@RequestParam("id") Long id) {
        BpmOATripDO trip = tripService.getTrip(id);
        return success(BeanUtils.toBean(trip, BpmOATripRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得出差申请分页")
    public CommonResult<PageResult<BpmOATripRespVO>> getTripPage(@Valid BpmOATripPageReqVO pageVO) {
        PageResult<BpmOATripDO> pageResult = tripService.getTripPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOATripRespVO.class));
    }

}
