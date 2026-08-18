package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.AssertTrue;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 项目立项申请创建 Request VO")
@Data
public class BpmOAProjectCreateReqVO {

    @Schema(description = "项目名称", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "项目名称不能为空")
    private String projectName;

    @Schema(description = "项目类型", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "项目类型不能为空")
    private String projectType;

    @Schema(description = "业主单位", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "业主单位不能为空")
    private String ownerUnit;

    @Schema(description = "项目来源", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "项目来源不能为空")
    private String projectSource;

    @Schema(description = "项目负责人", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "项目负责人不能为空")
    private Long projectLeaderId;

    @Schema(description = "项目概况", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "项目概况不能为空")
    private String projectOverview;

    @Schema(description = "合同金额/预估金额", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "合同金额/预估金额不能为空")
    private BigDecimal projectAmount;

    @Schema(description = "计划开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "计划开始时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime plannedStartTime;

    @Schema(description = "计划结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "计划结束时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime plannedEndTime;

    @Schema(description = "参与部门编号数组")
    private List<Long> participantDeptIds;

    @Schema(description = "风险说明")
    private String riskDescription;

    @Schema(description = "附件地址数组")
    private List<String> attachmentUrls;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

    @AssertTrue(message = "计划结束时间，需要在计划开始时间之后")
    public boolean isPlannedEndTimeValid() {
        return plannedStartTime != null
                && plannedEndTime != null
                && !plannedEndTime.isBefore(plannedStartTime);
    }

}
