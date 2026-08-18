package cn.iocoder.yudao.module.system.controller.admin.meetingroom.vo.room;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.experimental.Accessors;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 会议室新增/修改 Request VO")
@Data
@Accessors(chain = true)
public class MeetingRoomSaveReqVO {

    @Schema(description = "编号", example = "1024")
    private Long id;

    @Schema(description = "会议室名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "A101")
    @NotBlank(message = "会议室名称不能为空")
    private String name;

    @Schema(description = "所在位置", requiredMode = Schema.RequiredMode.REQUIRED, example = "1号楼 10层")
    @NotBlank(message = "所在位置不能为空")
    private String location;

    @Schema(description = "容纳人数", requiredMode = Schema.RequiredMode.REQUIRED, example = "12")
    @NotNull(message = "容纳人数不能为空")
    private Integer capacity;

    @Schema(description = "设备配置，逗号分隔", example = "projector,tv")
    private String equipment;

    @Schema(description = "备注", example = "靠窗")
    private String remark;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "状态不能为空")
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

    @Schema(description = "排序号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "排序号不能为空")
    private Integer sort;

}
