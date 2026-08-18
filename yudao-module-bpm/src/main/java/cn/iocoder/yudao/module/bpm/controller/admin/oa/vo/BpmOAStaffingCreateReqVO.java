package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 项目人员调配申请创建 Request VO")
@Data
public class BpmOAStaffingCreateReqVO {

    @Schema(description = "所属项目", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "所属项目不能为空")
    private String projectName;

    @Schema(description = "调入/调出人员编号数组", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotEmpty(message = "调入/调出人员不能为空")
    private List<Long> memberIds;

    @Schema(description = "调配原因", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "调配原因不能为空")
    private String reason;

    @Schema(description = "调配时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "调配时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime transferTime;

    @Schema(description = "预计工作周期", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "预计工作周期不能为空")
    private String expectedWorkPeriod;

    @Schema(description = "接收部门或项目组", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "接收部门或项目组不能为空")
    private String targetUnit;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

}
