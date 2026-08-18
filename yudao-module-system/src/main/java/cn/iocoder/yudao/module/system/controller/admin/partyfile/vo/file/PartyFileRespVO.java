package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 党务文件 Response VO")
@Data
public class PartyFileRespVO {

    private Long id;

    private String title;

    private Long categoryId;

    private String categoryName;

    private String summary;

    private String content;

    private String attachmentFileIds;

    private Integer storageType;

    private Long kodSourceId;

    private String kodFolderPath;

    private String kodFolderName;

    private Integer status;

    private LocalDateTime publishTime;

    private String creator;

    private LocalDateTime createTime;

    private Boolean readStatus;

    private Long readCount;

    private Long unreadCount;

    private List<PartyFileAttachmentRespVO> attachments;

    private List<PartyFileTargetRespVO> targets;

    private List<PartyFileReadRespVO> readList;

    private List<PartyFileUnreadRespVO> unreadList;
}
