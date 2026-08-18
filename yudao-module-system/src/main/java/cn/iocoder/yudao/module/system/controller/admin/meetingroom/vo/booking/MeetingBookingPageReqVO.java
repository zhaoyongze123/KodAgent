package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 会议室预定分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class MeetingBookingPageReqVO extends PageParam {

    @Schema(description = "会议室编号", example = "1")
    private Long meetingRoomId;

    @Schema(description = "申请人编号", example = "1")
    private Long applicantUserId;

    @Schema(description = "会议主题", example = "项目评审")
    private String subject;

    @Schema(description = "状态", example = "1")
    private Integer status;

    @Schema(description = "开始时间范围-开始")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTimeFrom;

    @Schema(description = "开始时间范围-结束")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTimeTo;

}
