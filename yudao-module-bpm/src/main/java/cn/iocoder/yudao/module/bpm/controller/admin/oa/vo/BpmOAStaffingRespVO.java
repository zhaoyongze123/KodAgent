package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 项目人员调配申请 Response VO")
@Data
public class BpmOAStaffingRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "申请人")
    private String applicantName;

    @Schema(description = "部门编号")
    private Long deptId;

    @Schema(description = "部门名称")
    private String deptName;

    @Schema(description = "所属项目")
    private String projectName;

    @Schema(description = "调入/调出人员编号 JSON")
    private String memberIds;

    @Schema(description = "调入/调出人员")
    private String memberNames;

    @Schema(description = "调配原因")
    private String reason;

    @Schema(description = "调配时间")
    private LocalDateTime transferTime;

    @Schema(description = "预计工作周期")
    private String expectedWorkPeriod;

    @Schema(description = "接收部门或项目组")
    private String targetUnit;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "申请时间")
    private LocalDateTime createTime;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

}
