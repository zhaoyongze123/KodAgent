package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 会议室 Response VO")
@Data
public class MeetingRoomRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "会议室名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "A101")
    private String name;

    @Schema(description = "所在位置", requiredMode = Schema.RequiredMode.REQUIRED, example = "1号楼 10层")
    private String location;

    @Schema(description = "容纳人数", requiredMode = Schema.RequiredMode.REQUIRED, example = "12")
    private Integer capacity;

    @Schema(description = "设备配置", example = "projector,tv")
    private String equipment;

    @Schema(description = "备注", example = "靠窗")
    private String remark;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    private Integer status;

    @Schema(description = "排序号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer sort;

    @Schema(description = "创建时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

}
