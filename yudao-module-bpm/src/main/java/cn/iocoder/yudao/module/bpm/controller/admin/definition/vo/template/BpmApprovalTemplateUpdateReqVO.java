package cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - BPM 审批模板更新 Request VO")
@Data
public class BpmApprovalTemplateUpdateReqVO {

    @Schema(description = "模板编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "模板编号不能为空")
    private Long id;

    @Schema(description = "模板名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "请假申请")
    @NotBlank(message = "模板名称不能为空")
    private String name;

    @Schema(description = "模板描述", example = "员工请假审批")
    private String description;

    @Schema(description = "模板图标", example = "solar:calendar-outline")
    private String icon;

    @Schema(description = "是否上架", requiredMode = Schema.RequiredMode.REQUIRED, example = "true")
    @NotNull(message = "上架状态不能为空")
    private Boolean visible;

    @Schema(description = "排序值", requiredMode = Schema.RequiredMode.REQUIRED, example = "10")
    @NotNull(message = "排序值不能为空")
    private Integer sort;

    @Schema(description = "绑定的流程定义编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "oa_leave:3:4")
    @NotBlank(message = "绑定的流程定义不能为空")
    private String processDefinitionId;

}
