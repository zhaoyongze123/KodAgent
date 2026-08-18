package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - 党务文件可道云目录来源分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class PartyFileKodSourcePageReqVO extends PageParam {

    @Schema(description = "来源名称")
    private String name;

    @Schema(description = "状态")
    private Integer status;
}
