package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 党务文件分类 Response VO")
@Data
public class PartyFileCategoryRespVO {

    @Schema(description = "分类编号", example = "1")
    private Long id;

    @Schema(description = "分类名称", example = "学习资料")
    private String name;

    @Schema(description = "父级编号", example = "0")
    private Long parentId;

    @Schema(description = "排序", example = "1")
    private Integer sort;

    @Schema(description = "状态", example = "0")
    private Integer status;

    @Schema(description = "创建时间")
    private LocalDateTime createTime;
}
