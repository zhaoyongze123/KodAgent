package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 临时外出申请分页 Request VO")
@Data
public class BpmOAOutingPageReqVO extends PageParam {

    @Schema(description = "状态", example = "1")
    private Integer status;

    @Schema(description = "外出类型", example = "1")
    private Integer type;

    @Schema(description = "外出事由", example = "项目现场踏勘")
    private String reason;

    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @Schema(description = "申请时间")
    private LocalDateTime[] createTime;

}
