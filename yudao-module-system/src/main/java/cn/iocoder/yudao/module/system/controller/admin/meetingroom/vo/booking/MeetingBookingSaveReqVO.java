package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking;

import com.fasterxml.jackson.annotation.JsonFormat;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.experimental.Accessors;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import java.time.LocalDateTime;
import java.util.List;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 会议室预定新增/修改 Request VO")
@Data
@Accessors(chain = true)
public class MeetingBookingSaveReqVO {

    @Schema(description = "编号", example = "1024")
    private Long id;

    @Schema(description = "会议主题", requiredMode = Schema.RequiredMode.REQUIRED, example = "项目评审")
    @NotBlank(message = "会议主题不能为空")
    private String subject;

    @Schema(description = "会议室编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "会议室不能为空")
    private Long meetingRoomId;

    @Schema(description = "开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "开始时间不能为空")
    @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTime;

    @Schema(description = "结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "结束时间不能为空")
    @JsonFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime endTime;

    @Schema(description = "参会人员编号列表", example = "[1,2]")
    private List<Long> attendeeUserIds;

    @Schema(description = "备注", example = "需视频会议")
    private String remark;

    @Schema(description = "是否忽略冲突提醒继续保存", example = "false")
    @NotNull(message = "是否忽略冲突提醒不能为空")
    private Boolean forceConflict;

}
