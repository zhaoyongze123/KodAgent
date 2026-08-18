package cn.iocoder.yudao.module.system.controller.admin.personalschedule.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 个人日程 Response VO")
@Data
public class PersonalScheduleRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "日程标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "外出调研")
    private String title;

    @Schema(description = "开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime startTime;

    @Schema(description = "结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime endTime;

    @Schema(description = "所属用户编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Long ownerUserId;

    @Schema(description = "地址", example = "上海客户现场")
    private String location;

    @Schema(description = "文字描述", example = "调研项目需求并现场访谈")
    private String description;

    @Schema(description = "参与人编号列表", example = "[1,2]")
    private List<Long> attendeeUserIds;

    @Schema(description = "参与人昵称列表", example = "[\"芋道\", \"源码\"]")
    private List<String> attendeeUserNicknames;

    @Schema(description = "外部参与者", example = "客户张三、客户李四")
    private String otherParticipants;

    @Schema(description = "创建时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

}
