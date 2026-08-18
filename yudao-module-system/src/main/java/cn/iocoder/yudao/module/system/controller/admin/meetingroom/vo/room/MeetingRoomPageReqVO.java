package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - 会议室分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class MeetingRoomPageReqVO extends PageParam {

    @Schema(description = "会议室名称", example = "A101")
    private String name;

    @Schema(description = "所在位置", example = "10层")
    private String location;

    @Schema(description = "状态", example = "0")
    private Integer status;

}
