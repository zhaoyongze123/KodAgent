package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.booking;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 会议室预定 Response VO")
@Data
public class MeetingBookingRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "会议主题", requiredMode = Schema.RequiredMode.REQUIRED, example = "项目评审")
    private String subject;

    @Schema(description = "会议室编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long meetingRoomId;

    @Schema(description = "会议室名称", example = "A101")
    private String meetingRoomName;

    @Schema(description = "开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime startTime;

    @Schema(description = "结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime endTime;

    @Schema(description = "申请人编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long applicantUserId;

    @Schema(description = "申请人昵称", example = "芋道")
    private String applicantUserNickname;

    @Schema(description = "参会人员编号列表", example = "[1,2]")
    private List<Long> attendeeUserIds;

    @Schema(description = "参会人员昵称列表", example = "[\"芋道\", \"源码\"]")
    private List<String> attendeeUserNicknames;

    @Schema(description = "备注", example = "需视频会议")
    private String remark;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

    @Schema(description = "是否忽略冲突提醒继续保存", example = "false")
    private Boolean forceConflict;

    @Schema(description = "取消原因", example = "会议取消")
    private String cancelReason;

    @Schema(description = "取消类型", example = "1")
    private Integer cancelType;

    @Schema(description = "创建时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

}
