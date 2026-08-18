package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 党务文件附件上传 Response VO")
@Data
public class PartyFileAttachmentUploadRespVO {

    private Long id;

    private String name;

    private String url;

    private Long size;

    private String type;
}
