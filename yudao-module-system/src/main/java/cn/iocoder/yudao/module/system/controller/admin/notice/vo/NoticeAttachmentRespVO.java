package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 通知公告附件 Response VO")
@Data
public class NoticeAttachmentRespVO {

    @Schema(description = "文件编号", example = "1")
    private Long id;

    @Schema(description = "文件名称", example = "制度说明.pdf")
    private String name;

    @Schema(description = "文件地址", example = "https://example.com/file.pdf")
    private String url;

    @Schema(description = "文件大小", example = "2048")
    private Long size;

    @Schema(description = "文件类型", example = "application/pdf")
    private String type;
}
