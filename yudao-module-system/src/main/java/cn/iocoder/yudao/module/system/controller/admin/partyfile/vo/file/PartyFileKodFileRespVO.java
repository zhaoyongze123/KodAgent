package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 可道云文件 Response VO")
@Data
public class PartyFileKodFileRespVO {

    @Schema(description = "文件名", requiredMode = Schema.RequiredMode.REQUIRED)
    private String name;

    @Schema(description = "文件路径", requiredMode = Schema.RequiredMode.REQUIRED)
    private String path;

    @Schema(description = "文件显示路径")
    private String pathDisplay;

    @Schema(description = "文件大小")
    private Long size;

    @Schema(description = "文件类型")
    private String type;
}
