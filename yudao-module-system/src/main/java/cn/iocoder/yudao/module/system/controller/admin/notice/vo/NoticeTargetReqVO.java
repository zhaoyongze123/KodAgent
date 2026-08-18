package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 通知公告分发对象 Request VO")
@Data
public class NoticeTargetReqVO {

    @Schema(description = "分发类型 1全员 2用户 3部门 4角色", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer targetType;

    @Schema(description = "分发对象编号，选择全员时可为空", example = "1")
    private Long targetId;
}
