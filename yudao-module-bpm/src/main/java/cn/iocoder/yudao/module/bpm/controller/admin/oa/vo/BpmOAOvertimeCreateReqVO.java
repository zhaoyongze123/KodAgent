package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.AssertTrue;
import javax.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 加班申请创建 Request VO")
@Data
public class BpmOAOvertimeCreateReqVO {

    @Schema(description = "加班的开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "开始时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTime;

    @Schema(description = "加班的结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "结束时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime endTime;

    @Schema(description = "加班类型-参见 bpm_oa_type 枚举", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer type;

    @Schema(description = "加班日期", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDate workDate;

    @Schema(description = "原因", requiredMode = Schema.RequiredMode.REQUIRED, example = "阅读芋道源码")
    private String reason;

    @Schema(description = "加班时长（小时）", requiredMode = Schema.RequiredMode.REQUIRED, example = "3.5")
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

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

    @AssertTrue(message = "结束时间，需要在开始时间之后")
    public boolean isEndTimeValid() {
        return !getEndTime().isBefore(getStartTime());
    }

}
