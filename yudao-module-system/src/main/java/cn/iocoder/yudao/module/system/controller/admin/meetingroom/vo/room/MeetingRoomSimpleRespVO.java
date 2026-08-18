package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Schema(description = "管理后台 - 会议室精简 Response VO")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class MeetingRoomSimpleRespVO {

    @Schema(description = "编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "会议室名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "A101")
    private String name;

    @Schema(description = "所在位置", example = "1号楼 10层")
    private String location;

}
