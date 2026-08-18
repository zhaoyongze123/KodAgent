package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 党务文件可道云文件列表 Request VO")
@Data
public class PartyFileKodFilesReqVO {

    @Schema(description = "可道云目录来源编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "2")
    @NotNull(message = "可道云目录来源编号不能为空")
    private Long kodSourceId;

    @Schema(description = "可道云目录路径", requiredMode = Schema.RequiredMode.REQUIRED, example = "{source:7}/")
    @NotBlank(message = "可道云目录路径不能为空")
    private String kodFolderPath;
}
