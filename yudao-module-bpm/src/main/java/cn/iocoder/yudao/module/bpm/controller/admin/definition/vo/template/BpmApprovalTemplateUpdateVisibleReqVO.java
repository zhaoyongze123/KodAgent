package cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - BPM 审批模板上下架 Request VO")
@Data
public class BpmApprovalTemplateUpdateVisibleReqVO {

    @Schema(description = "模板编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "模板编号不能为空")
    private Long id;

    @Schema(description = "是否上架", requiredMode = Schema.RequiredMode.REQUIRED, example = "true")
    @NotNull(message = "上架状态不能为空")
    private Boolean visible;

}
