package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import java.util.List;

@Schema(description = "管理后台 - 选择可道云附件 Request VO")
@Data
public class PartyFileKodSelectReqVO {

    @Schema(description = "可道云来源编号", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "可道云来源不能为空")
    private Long kodSourceId;

    @Schema(description = "当前目录路径", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "当前目录不能为空")
    private String kodFolderPath;

    @Schema(description = "选择的文件列表", requiredMode = Schema.RequiredMode.REQUIRED)
    @Valid
    @NotEmpty(message = "请选择至少一个文件")
    private List<PartyFileKodSelectFileReqVO> files;
}
