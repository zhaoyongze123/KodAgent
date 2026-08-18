package cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - BPM 审批模板 Response VO")
@Data
public class BpmApprovalTemplateRespVO {

    @Schema(description = "模板编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long id;

    @Schema(description = "模板编码", requiredMode = Schema.RequiredMode.REQUIRED, example = "oa_leave")
    private String code;

    @Schema(description = "模板名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "请假申请")
    private String name;

    @Schema(description = "模板描述", example = "员工请假审批")
    private String description;

    @Schema(description = "模板图标", example = "solar:calendar-outline")
    private String icon;

    @Schema(description = "流程分类编码", requiredMode = Schema.RequiredMode.REQUIRED, example = "oa_leave")
    private String category;

    @Schema(description = "流程分类名称", example = "请假")
    private String categoryName;

    @Schema(description = "是否上架", requiredMode = Schema.RequiredMode.REQUIRED, example = "true")
    private Boolean visible;

    @Schema(description = "排序值", requiredMode = Schema.RequiredMode.REQUIRED, example = "10")
    private Integer sort;

    @Schema(description = "绑定的流程定义编号", example = "oa_leave:3:4")
    private String processDefinitionId;

    @Schema(description = "绑定的流程定义标识", example = "oa_leave")
    private String processDefinitionKey;

    @Schema(description = "绑定的流程定义名称", example = "请假申请")
    private String processDefinitionName;

    @Schema(description = "绑定的流程模型编号", example = "8f2b5f0c-...")
    private String modelId;

    @Schema(description = "流程模型类型", example = "10")
    private Integer modelType;

    @Schema(description = "表单类型", example = "10")
    private Integer formType;

    @Schema(description = "流程状态", example = "1")
    private Integer suspensionState;

    @Schema(description = "部署时间")
    private LocalDateTime deploymentTime;

    @Schema(description = "创建时间")
    private LocalDateTime createTime;

}
