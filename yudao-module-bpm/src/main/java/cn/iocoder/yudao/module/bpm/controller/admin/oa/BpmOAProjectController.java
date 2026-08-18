package cn.iocoder.yudao.module.bpm.controller.admin.oa;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectPageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOAProjectRespVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOAProjectDO;
import cn.iocoder.yudao.module.bpm.service.oa.BpmOAProjectService;
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

@Tag(name = "管理后台 - OA 项目立项申请")
@RestController
@RequestMapping("/bpm/oa/project")
@Validated
public class BpmOAProjectController {

    @Resource
    private BpmOAProjectService projectService;

    @PostMapping("/create")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:create')")
    @Operation(summary = "创建项目立项申请")
    public CommonResult<Long> createProject(@Valid @RequestBody BpmOAProjectCreateReqVO createReqVO) {
        return success(projectService.createProject(getLoginUserId(), createReqVO));
    }

    @GetMapping("/get")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得项目立项申请")
    @Parameter(name = "id", description = "编号", required = true, example = "1024")
    public CommonResult<BpmOAProjectRespVO> getProject(@RequestParam("id") Long id) {
        BpmOAProjectDO project = projectService.getProject(id);
        return success(BeanUtils.toBean(project, BpmOAProjectRespVO.class));
    }

    @GetMapping("/page")
    @PreAuthorize("@ss.hasPermission('bpm:oa-leave:query')")
    @Operation(summary = "获得项目立项申请分页")
    public CommonResult<PageResult<BpmOAProjectRespVO>> getProjectPage(@Valid BpmOAProjectPageReqVO pageVO) {
        PageResult<BpmOAProjectDO> pageResult = projectService.getProjectPage(getLoginUserId(), pageVO);
        return success(BeanUtils.toBean(pageResult, BpmOAProjectRespVO.class));
    }

}
