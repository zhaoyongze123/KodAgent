package cn.iocoder.yudao.module.system.controller.admin.notice.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 通知公告信息 Response VO")
@Data
public class NoticeRespVO {

    @Schema(description = "通知公告序号", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "公告标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "小博主")
    private String title;

    @Schema(description = "公告类型", requiredMode = Schema.RequiredMode.REQUIRED, example = "小博主")
    private Integer type;

    @Schema(description = "公告内容", requiredMode = Schema.RequiredMode.REQUIRED, example = "半生编码")
    private String content;

    @Schema(description = "发布对象", example = "全体后台用户")
    private String publishTarget;

    @Schema(description = "是否置顶", example = "false")
    private Boolean pinned;

    @Schema(description = "附件文件编号列表，逗号分隔", example = "1,2,3")
    private String attachmentFileIds;

    @Schema(description = "状态，参见 CommonStatusEnum 枚举类", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

    @Schema(description = "发布人", example = "admin")
    private String creator;

    @Schema(description = "创建时间", requiredMode = Schema.RequiredMode.REQUIRED, example = "时间戳格式")
    private LocalDateTime createTime;

    @Schema(description = "附件列表")
    private List<NoticeAttachmentRespVO> attachments;

    @Schema(description = "阅读人数", example = "12")
    private Long readCount;

    @Schema(description = "未读人数", example = "4")
    private Long unreadCount;

    @Schema(description = "分发对象")
    private List<NoticeTargetRespVO> targets;

    @Schema(description = "阅读明细")
    private List<NoticeReadRespVO> readList;

    @Schema(description = "未读明细")
    private List<NoticeUnreadRespVO> unreadList;

}
