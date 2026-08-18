package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 党务文件阅读明细 Response VO")
@Data
public class PartyFileReadRespVO {

    private Long userId;

    private String userNickname;

    private Long deptId;

    private String deptName;

    private LocalDateTime readTime;

    private Integer readSource;
}
