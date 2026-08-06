package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;

@Schema(description = "管理后台 - 通知公告创建/修改 Request VO")
@Data
public class NoticeSaveReqVO {

    @Schema(description = "岗位公告编号", example = "1024")
    private Long id;

    @Schema(description = "公告标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "小博主")
    @NotBlank(message = "公告标题不能为空")
    @Size(max = 50, message = "公告标题不能超过50个字符")
    private String title;

    @Schema(description = "公告类型", requiredMode = Schema.RequiredMode.REQUIRED, example = "小博主")
    @NotNull(message = "公告类型不能为空")
    private Integer type;

    @Schema(description = "公告内容", requiredMode = Schema.RequiredMode.REQUIRED, example = "半生编码")
    private String content;

    @Schema(description = "发布对象", example = "全体后台用户")
    @Size(max = 255, message = "发布对象不能超过255个字符")
    private String publishTarget;

    @Schema(description = "结构化分发对象")
    private List<NoticeTargetReqVO> targets;

    @Schema(description = "是否置顶", example = "false")
    private Boolean pinned;

    @Schema(description = "附件文件编号列表，逗号分隔", example = "1,2,3")
    @Size(max = 512, message = "附件文件编号列表长度不能超过512个字符")
    private String attachmentFileIds;

    @Schema(description = "状态，参见 CommonStatusEnum 枚举类", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

}
