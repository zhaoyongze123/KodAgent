package cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.model;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 流程模型更新展示状态 Request VO")
@Data
public class BpmModelUpdateVisibleReqVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    @NotNull(message = "编号不能为空")
    private String id;

    @Schema(description = "是否展示在发起审批里", requiredMode = Schema.RequiredMode.REQUIRED, example = "true")
    @NotNull(message = "是否展示不能为空")
    private Boolean visible;

}
