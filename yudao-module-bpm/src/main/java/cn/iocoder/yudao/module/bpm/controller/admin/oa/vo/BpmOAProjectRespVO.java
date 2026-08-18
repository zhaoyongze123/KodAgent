package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Schema(description = "管理后台 - 项目立项申请 Response VO")
@Data
public class BpmOAProjectRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "申请人")
    private String applicantName;

    @Schema(description = "部门编号")
    private Long deptId;

    @Schema(description = "部门名称")
    private String deptName;

    @Schema(description = "项目名称")
    private String projectName;

    @Schema(description = "项目类型")
    private String projectType;

    @Schema(description = "业主单位")
    private String ownerUnit;

    @Schema(description = "项目来源")
    private String projectSource;

    @Schema(description = "项目负责人编号")
    private Long projectLeaderId;

    @Schema(description = "项目负责人")
    private String projectLeaderName;

    @Schema(description = "项目概况")
    private String projectOverview;

    @Schema(description = "合同金额/预估金额")
    private BigDecimal projectAmount;

    @Schema(description = "计划开始时间")
    private LocalDateTime plannedStartTime;

    @Schema(description = "计划结束时间")
    private LocalDateTime plannedEndTime;

    @Schema(description = "参与部门编号 JSON")
    private String participantDeptIds;

    @Schema(description = "参与部门名称")
    private String participantDeptNames;

    @Schema(description = "风险说明")
    private String riskDescription;

    @Schema(description = "附件地址 JSON")
    private String attachmentUrls;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "申请时间")
    private LocalDateTime createTime;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

}
