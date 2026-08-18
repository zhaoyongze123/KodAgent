package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - 党务文件可道云目录来源创建/修改 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class PartyFileKodSourceSaveReqVO extends PartyFileKodSourceBaseVO {

    @Schema(description = "来源编号")
    private Long id;
}
