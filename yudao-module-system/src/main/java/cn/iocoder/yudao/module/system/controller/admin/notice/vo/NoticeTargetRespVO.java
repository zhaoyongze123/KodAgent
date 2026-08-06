package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 通知公告分发对象 Response VO")
@Data
public class NoticeTargetRespVO {

    @Schema(description = "分发类型 1全员 2用户 3部门 4角色", example = "1")
    private Integer targetType;

    @Schema(description = "分发对象编号", example = "1")
    private Long targetId;

    @Schema(description = "分发对象名称", example = "院部")
    private String targetName;
}
