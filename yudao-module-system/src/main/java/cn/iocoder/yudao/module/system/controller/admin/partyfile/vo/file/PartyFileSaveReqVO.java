package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 党务文件创建/修改 Request VO")
@Data
public class PartyFileSaveReqVO {

    @Schema(description = "文件编号", example = "1")
    private Long id;

    @Schema(description = "标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "6 月主题党日资料")
    @NotBlank(message = "标题不能为空")
    @Size(max = 100, message = "标题不能超过 100 个字符")
    private String title;

    @Schema(description = "分类编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "分类不能为空")
    private Long categoryId;

    @Schema(description = "摘要", example = "请全体党员本周内完成学习")
    @Size(max = 255, message = "摘要不能超过 255 个字符")
    private String summary;

    @Schema(description = "正文", example = "<p>正文内容</p>")
    private String content;

    @Schema(description = "附件编号列表，逗号分隔", example = "1,2,3")
    private String attachmentFileIds;

    @Schema(description = "存储类型 1本地 2可道云", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "存储类型不能为空")
    private Integer storageType;

    @Schema(description = "可道云来源编号", example = "1")
    private Long kodSourceId;

    @Schema(description = "可道云目录路径", example = "{source:1001}/党务通知")
    private String kodFolderPath;

    @Schema(description = "可道云目录名称", example = "党务通知")
    private String kodFolderName;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "状态不能为空")
    private Integer status;

    @Schema(description = "发布时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "发布时间不能为空")
    private LocalDateTime publishTime;

    @Schema(description = "分发对象", requiredMode = Schema.RequiredMode.REQUIRED)
    @Valid
    @NotEmpty(message = "分发对象不能为空")
    private List<PartyFileTargetReqVO> targets;
}
