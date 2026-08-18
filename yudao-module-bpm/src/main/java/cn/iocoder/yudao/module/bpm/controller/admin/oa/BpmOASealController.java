package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOASealRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOASealDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOASealService;
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
 * OA 用章申请 Controller，用于演示自己存储数据，接入工作流的例子
 *
 * @author jason
 * @author 芋道源码
 */
@Tag(name = "管理后台 - OA 用章申请")
@RestController
@RequestMapping("/bpm/oa/seal")
@Validated
public class BpmOASealController {

    @Resource
    private BpmOASealService sealService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建请求申请")
    public CommonResult<Long> createSeal(@Valid @RequestBody BpmOASealCreateReqVO createReqVO) {
        return success(sealService.createSeal(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得用章申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOASealRespVO> getSeal(@RequestParam("id") Long id) {
        BpmOASealDO seal = sealService.getSeal(id);
        return success(BeanUtils.toBean(seal, BpmOASealRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得用章申请分页")
    public CommonResult<PageResult<BpmOASealRespVO>> getSealPage(@Valid BpmOASealPageReqVO pageVO) {
        PageResult<BpmOASealDO> pageResult = sealService.getSealPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOASealRespVO.class));
    }

}
