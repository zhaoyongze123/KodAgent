package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;

@Data
public class PartyFileCategoryBaseVO {

    @Schema(description = "分类名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "学习资料")
    @NotBlank(message = "分类名称不能为空")
    @Size(max = 64, message = "分类名称不能超过 64 个字符")
    private String name;

    @Schema(description = "父级编号", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "父级编号不能为空")
    private Long parentId;

    @Schema(description = "排序", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "排序不能为空")
    private Integer sort;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "状态不能为空")
    private Integer status;
}
