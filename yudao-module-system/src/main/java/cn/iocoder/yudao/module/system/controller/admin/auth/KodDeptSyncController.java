package cn.iocoder.yudao.module.system.controller.admin.auth;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.KodDeptSyncRespVO;
import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoProperties;
import cn.iocoder.yudao.module.system.service.auth.KodDeptSyncService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 可道云组织同步")
@RestController
@RequestMapping("/system/auth/kod-dept-sync")
@Validated
public class KodDeptSyncController {

    @Resource
    private KodDeptSyncService kodDeptSyncService;
    @Resource
    private KodSsoProperties kodSsoProperties;

    @PostMapping("/sync")
    @Operation(summary = "同步可道云组织树和部门文件空间")
    @PreAuthorize("@ss.hasAnyPermissions('system:kod-dept-sync:execute', 'system:party-file:update')")
    public CommonResult<KodDeptSyncRespVO> sync() {
        Long tenantId = TenantContextHolder.getTenantId();
        if (tenantId == null) {
            tenantId = kodSsoProperties.getTenantId();
        }
        return success(kodDeptSyncService.sync(tenantId));
    }
}
