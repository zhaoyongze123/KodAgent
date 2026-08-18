package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 会议室预定冲突 Response VO")
@Data
public class MeetingBookingConflictRespVO {

    @Schema(description = "预定编号", example = "1024")
    private Long id;

    @Schema(description = "会议主题", example = "项目评审")
    private String subject;

    @Schema(description = "会议室编号", example = "1")
    private Long meetingRoomId;

    @Schema(description = "会议室名称", example = "A101")
    private String meetingRoomName;

    @Schema(description = "申请人编号", example = "1")
    private Long applicantUserId;

    @Schema(description = "申请人昵称", example = "芋道")
    private String applicantUserNickname;

    @Schema(description = "开始时间")
    private LocalDateTime startTime;

    @Schema(description = "结束时间")
    private LocalDateTime endTime;

}
