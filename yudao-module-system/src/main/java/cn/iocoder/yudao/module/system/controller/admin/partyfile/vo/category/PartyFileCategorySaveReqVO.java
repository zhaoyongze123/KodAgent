package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

import javax.validation.constraints.NotNull;

@Schema(description = "管理后台 - 党务文件分类创建/修改 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class PartyFileCategorySaveReqVO extends PartyFileCategoryBaseVO {

    @Schema(description = "分类编号", example = "1")
    private Long id;
}
