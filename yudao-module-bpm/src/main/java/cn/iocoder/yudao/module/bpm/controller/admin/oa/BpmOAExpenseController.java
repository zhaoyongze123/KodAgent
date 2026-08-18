package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpenseCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpensePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAExpenseRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAExpenseDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAExpenseService;
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
 * OA 报销申请 Controller，用于演示自己存储数据，接入工作流的例子
 *
 * @author jason
 * @author 芋道源码
 */
@Tag(name = "管理后台 - OA 报销申请")
@RestController
@RequestMapping("/bpm/oa/expense")
@Validated
public class BpmOAExpenseController {

    @Resource
    private BpmOAExpenseService expenseService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建请求申请")
    public CommonResult<Long> createExpense(@Valid @RequestBody BpmOAExpenseCreateReqVO createReqVO) {
        return success(expenseService.createExpense(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得报销申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAExpenseRespVO> getExpense(@RequestParam("id") Long id) {
        BpmOAExpenseDO expense = expenseService.getExpense(id);
        return success(BeanUtils.toBean(expense, BpmOAExpenseRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得报销申请分页")
    public CommonResult<PageResult<BpmOAExpenseRespVO>> getExpensePage(@Valid BpmOAExpensePageReqVO pageVO) {
        PageResult<BpmOAExpenseDO> pageResult = expenseService.getExpensePage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAExpenseRespVO.class));
    }

}
