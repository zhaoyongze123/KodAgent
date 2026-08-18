package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 党务文件分发对象 Request VO")
@Data
public class PartyFileTargetReqVO {

    @Schema(description = "分发类型 1全员 2用户 3部门 4角色", requiredMode = Schema.RequiredMode.REQUIRED, example = "2")
    @NotNull(message = "分发类型不能为空")
    private Integer targetType;

    @Schema(description = "分发对象编号；全员时可为空", example = "100")
    private Long targetId;
}
