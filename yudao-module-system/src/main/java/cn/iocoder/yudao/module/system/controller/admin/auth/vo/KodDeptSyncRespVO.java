package cn.iocoder.yudao.module.system.controller.admin.auth.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 可道云组织同步结果")
@Data
public class KodDeptSyncRespVO {

    @Schema(description = "是否成功")
    private Boolean success;

    @Schema(description = "同步部门数量")
    private Integer departmentCount;

    @Schema(description = "同步用户数量")
    private Integer userCount;

    @Schema(description = "补齐部门空间数量")
    private Integer createdSourceCount;

    @Schema(description = "撤销旧部门权限数量")
    private Integer revokedPermissionCount;

    @Schema(description = "结果说明")
    private String message;
}
