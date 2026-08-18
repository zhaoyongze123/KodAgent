package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 党务文件分发对象 Response VO")
@Data
public class PartyFileTargetRespVO {

    private Integer targetType;

    private Long targetId;

    private String targetName;
}
