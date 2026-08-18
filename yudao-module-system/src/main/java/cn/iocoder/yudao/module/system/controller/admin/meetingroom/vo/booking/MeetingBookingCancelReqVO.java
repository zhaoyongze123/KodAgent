package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 会议室预定取消 Request VO")
@Data
public class MeetingBookingCancelReqVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    @NotNull(message = "编号不能为空")
    private Long id;

    @Schema(description = "取消原因", example = "会议取消")
    private String cancelReason;

}
