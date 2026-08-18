package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Schema(description = "管理后台 - 合同/文件审批 Response VO")
@Data
public class BpmOADocumentRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "申请人")
    private String applicantName;

    @Schema(description = "部门编号")
    private Long deptId;

    @Schema(description = "部门名称")
    private String deptName;

    @Schema(description = "文件类型")
    private String fileType;

    @Schema(description = "文件标题")
    private String title;

    @Schema(description = "关联项目")
    private String relatedProject;

    @Schema(description = "对方单位")
    private String counterpartUnit;

    @Schema(description = "金额")
    private BigDecimal amount;

    @Schema(description = "审批事由")
    private String reason;

    @Schema(description = "附件正文地址 JSON")
    private String attachmentBodyUrls;

    @Schema(description = "附件补充材料地址 JSON")
    private String attachmentExtraUrls;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "申请时间")
    private LocalDateTime createTime;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

}
