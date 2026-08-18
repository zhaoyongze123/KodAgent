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

@Schema(description = "管理后台 - 临时外出申请创建 Request VO")
@Data
public class BpmOAOutingCreateReqVO {

    @Schema(description = "外出开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "开始时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTime;

    @Schema(description = "外出结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "结束时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime endTime;

    @Schema(description = "外出类型", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer type;

    @Schema(description = "外出日期", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "外出日期不能为空")
    private LocalDate outingDate;

    @Schema(description = "外出时长（小时）", requiredMode = Schema.RequiredMode.REQUIRED, example = "2.5")
    private BigDecimal durationHours;

    @Schema(description = "外出地点", requiredMode = Schema.RequiredMode.REQUIRED, example = "市资规局")
    private String destination;

    @Schema(description = "是否离院", example = "true")
    private Boolean outsideOffice;

    @Schema(description = "联系电话", example = "13800000000")
    private String contactMobile;

    @Schema(description = "同行人员", example = "张三、李四")
    private String companionNames;

    @Schema(description = "外出事由", requiredMode = Schema.RequiredMode.REQUIRED, example = "项目现场踏勘")
    private String reason;

    @Schema(description = "备注", example = "预计下午返回")
    private String remark;

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

    @AssertTrue(message = "结束时间，需要在开始时间之后")
    public boolean isEndTimeValid() {
        return startTime == null || endTime == null || !endTime.isBefore(startTime);
    }

}
