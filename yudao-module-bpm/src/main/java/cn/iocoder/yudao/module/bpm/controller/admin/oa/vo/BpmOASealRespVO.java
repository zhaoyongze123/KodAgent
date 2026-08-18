package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 用章申请 Response VO")
@Data
public class BpmOASealRespVO {

    @Schema(description = "用章表单主键", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "申请人")
    private String applicantName;

    @Schema(description = "部门编号")
    private Long deptId;

    @Schema(description = "部门名称")
    private String deptName;

    @Schema(description = "用章类型，参见 bpm_oa_type 枚举", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer type;

    @Schema(description = "文件名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "规划成果报告")
    private String fileName;

    @Schema(description = "文件份数", requiredMode = Schema.RequiredMode.REQUIRED, example = "2")
    private Integer fileCount;

    @Schema(description = "原因", requiredMode = Schema.RequiredMode.REQUIRED, example = "阅读芋道源码")
    private String reason;

    @Schema(description = "申请时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

    @Schema(description = "使用时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime startTime;

    @Schema(description = "对方单位")
    private String counterpartUnit;

    @Schema(description = "是否外带")
    private Boolean externalCarry;

    @Schema(description = "经办人")
    private String operatorName;

    @Schema(description = "附件地址，多个使用 JSON 数组字符串存储")
    private String attachmentUrls;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status; // 参见 BpmProcessInstanceStatusEnum 枚举

}
