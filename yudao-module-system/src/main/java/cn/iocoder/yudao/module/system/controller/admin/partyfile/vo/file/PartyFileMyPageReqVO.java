package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "员工端 - 我的党务文件分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class PartyFileMyPageReqVO extends PageParam {

    @Schema(description = "标题", example = "主题党日")
    private String title;

    @Schema(description = "分类编号", example = "1")
    private Long categoryId;

    @Schema(description = "是否已读", example = "true")
    private Boolean readStatus;
}
