package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 通知公告阅读明细 Response VO")
@Data
public class NoticeReadRespVO {

    @Schema(description = "用户编号", example = "1")
    private Long userId;

    @Schema(description = "用户姓名", example = "Administrator")
    private String userNickname;

    @Schema(description = "部门编号", example = "10")
    private Long deptId;

    @Schema(description = "部门名称", example = "院部")
    private String deptName;

    @Schema(description = "阅读时间")
    private LocalDateTime readTime;
}
