package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendanceCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendancePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAAttendanceRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAAttendanceDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAAttendanceService;
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
 * OA 补卡申请 Controller，用于演示自己存储数据，接入工作流的例子
 *
 * @author jason
 * @author 芋道源码
 */
@Tag(name = "管理后台 - OA 补卡申请")
@RestController
@RequestMapping("/bpm/oa/attendance")
@Validated
public class BpmOAAttendanceController {

    @Resource
    private BpmOAAttendanceService attendanceService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建请求申请")
    public CommonResult<Long> createAttendance(@Valid @RequestBody BpmOAAttendanceCreateReqVO createReqVO) {
        return success(attendanceService.createAttendance(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得补卡申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAAttendanceRespVO> getAttendance(@RequestParam("id") Long id) {
        BpmOAAttendanceDO attendance = attendanceService.getAttendance(id);
        return success(BeanUtils.toBean(attendance, BpmOAAttendanceRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得补卡申请分页")
    public CommonResult<PageResult<BpmOAAttendanceRespVO>> getAttendancePage(@Valid BpmOAAttendancePageReqVO pageVO) {
        PageResult<BpmOAAttendanceDO> pageResult = attendanceService.getAttendancePage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAAttendanceRespVO.class));
    }

}
