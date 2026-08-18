package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 党务文件附件 Response VO")
@Data
public class PartyFileAttachmentRespVO {

    private Long id;

    private String name;

    private String url;

    private Long size;

    private String type;
}
