package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@Schema(description = "管理后台 - 加班申请 Response VO")
@Data
public class BpmOAOvertimeRespVO {

    @Schema(description = "加班表单主键", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "加班类型，参见 bpm_oa_type 枚举", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer type;

    @Schema(description = "加班日期", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDate workDate;

    @Schema(description = "原因", requiredMode = Schema.RequiredMode.REQUIRED, example = "阅读芋道源码")
    private String reason;

    @Schema(description = "申请时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

    @Schema(description = "加班的开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime startTime;

    @Schema(description = "加班的结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime endTime;

    @Schema(description = "加班时长（小时）", example = "3.5")
    private BigDecimal durationHours;

    @Schema(description = "加班地点", example = "院内办公室")
    private String workLocation;

    @Schema(description = "加班内容", example = "整理阶段成果并提交")
    private String workContent;

    @Schema(description = "补偿方式", example = "1")
    private Integer compensationType;

    @Schema(description = "关联项目", example = "国土空间总体规划")
    private String projectName;

    @Schema(description = "备注", example = "请优先安排调休")
    private String remark;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status; // 参见 BpmProcessInstanceStatusEnum 枚举

}
