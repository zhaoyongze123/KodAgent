package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 项目立项申请分页 Request VO")
@Data
public class BpmOAProjectPageReqVO extends PageParam {

    @Schema(description = "状态", example = "1")
    private Integer status;

    @Schema(description = "项目名称", example = "城市更新专项规划")
    private String projectName;

    @Schema(description = "项目类型", example = "详细规划")
    private String projectType;

    @Schema(description = "业主单位", example = "某规划局")
    private String ownerUnit;

    @Schema(description = "项目负责人", example = "张三")
    private String projectLeaderName;

    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @Schema(description = "申请时间")
    private LocalDateTime[] createTime;

}
