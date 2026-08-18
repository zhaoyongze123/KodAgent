package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 党务文件未读人员 Response VO")
@Data
public class PartyFileUnreadRespVO {

    private Long userId;

    private String userNickname;

    private Long deptId;

    private String deptName;
}
