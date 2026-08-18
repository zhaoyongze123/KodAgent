package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;

@Schema(description = "管理后台 - 选择可道云附件文件 Request VO")
@Data
public class PartyFileKodSelectFileReqVO {

    @Schema(description = "文件名", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "文件名不能为空")
    private String name;

    @Schema(description = "文件路径", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "文件路径不能为空")
    private String path;

    @Schema(description = "文件大小")
    private Long size;

    @Schema(description = "文件类型")
    private String type;
}
