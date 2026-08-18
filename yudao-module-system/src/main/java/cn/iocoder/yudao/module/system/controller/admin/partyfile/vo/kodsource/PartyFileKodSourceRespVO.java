package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 党务文件可道云目录来源 Response VO")
@Data
public class PartyFileKodSourceRespVO {

    private Long id;

    private String name;

    private String baseUrl;

    private String appName;

    private String accessToken;

    private String serviceUsername;

    private String servicePassword;

    private Boolean hasServicePassword;

    private LocalDateTime tokenExpireTime;

    private String rootFolderPath;

    private String rootFolderName;

    private Integer status;

    private Boolean isDefault;

    private LocalDateTime createTime;
}
