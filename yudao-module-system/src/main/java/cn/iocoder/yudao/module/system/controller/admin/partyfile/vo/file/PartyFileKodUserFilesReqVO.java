package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;

@Schema(description = "管理后台 - 当前用户可道云文件列表 Request VO")
@Data
public class PartyFileKodUserFilesReqVO {

    @Schema(description = "目录路径，根目录使用 /", requiredMode = Schema.RequiredMode.REQUIRED, example = "/")
    @NotBlank(message = "可道云目录不能为空")
    private String kodFolderPath;
}
