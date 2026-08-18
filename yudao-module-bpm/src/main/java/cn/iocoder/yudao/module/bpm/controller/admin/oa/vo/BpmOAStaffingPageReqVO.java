package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 项目人员调配申请分页 Request VO")
@Data
public class BpmOAStaffingPageReqVO extends PageParam {

    @Schema(description = "状态", example = "1")
    private Integer status;

    @Schema(description = "所属项目", example = "城市更新专项规划")
    private String projectName;

    @Schema(description = "调配原因", example = "阶段资源增补")
    private String reason;

    @Schema(description = "接收部门或项目组", example = "总体规划一所")
    private String targetUnit;

    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @Schema(description = "申请时间")
    private LocalDateTime[] createTime;

}
