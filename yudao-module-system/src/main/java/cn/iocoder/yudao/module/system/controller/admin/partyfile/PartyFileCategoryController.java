package cn.iocoder.yudao.module.system.controller.admin.partyfile;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category.PartyFileCategoryRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category.PartyFileCategorySaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileCategoryDO;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileCategoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.List;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 党务文件分类")
@RestController
@RequestMapping("/system/party-file-category")
@Validated
public class PartyFileCategoryController {

    @Resource
    private PartyFileCategoryService categoryService;

    @PostMapping("/create")
    @Operation(summary = "创建党务文件分类")
    @PreAuthorize("@ss.hasPermission('system:party-file-category:create')")
    public CommonResult<Long> create(@Valid @RequestBody PartyFileCategorySaveReqVO reqVO) {
        return success(categoryService.createCategory(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改党务文件分类")
    @PreAuthorize("@ss.hasPermission('system:party-file-category:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody PartyFileCategorySaveReqVO reqVO) {
        categoryService.updateCategory(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除党务文件分类")
    @PreAuthorize("@ss.hasPermission('system:party-file-category:delete')")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        categoryService.deleteCategory(id);
        return success(true);
    }

    @GetMapping("/list")
    @Operation(summary = "获取党务文件分类列表")
    @PreAuthorize("@ss.hasPermission('system:party-file-category:query')")
    public CommonResult<List<PartyFileCategoryRespVO>> list(@RequestParam(value = "status", required = false) Integer status) {
        List<PartyFileCategoryDO> list = categoryService.getCategoryList(status);
        return success(BeanUtils.toBean(list, PartyFileCategoryRespVO.class));
    }

    @GetMapping("/simple-list")
    @Operation(summary = "获取党务文件分类精简列表")
    public CommonResult<List<PartyFileCategoryRespVO>> simpleList() {
        List<PartyFileCategoryDO> list = categoryService.getCategoryList(CommonStatusEnum.ENABLE.getStatus());
        return success(BeanUtils.toBean(list, PartyFileCategoryRespVO.class));
    }

    @GetMapping("/get")
    @Operation(summary = "获取党务文件分类详情")
    @PreAuthorize("@ss.hasPermission('system:party-file-category:query')")
    public CommonResult<PartyFileCategoryRespVO> get(@RequestParam("id") Long id) {
        return success(BeanUtils.toBean(categoryService.getCategory(id), PartyFileCategoryRespVO.class));
    }
}
