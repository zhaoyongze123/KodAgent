package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 用章申请分页 Request VO")
@Data
public class BpmOASealPageReqVO extends PageParam {

    @Schema(description = "状态", example = "1")
    private Integer status; // 参见 BpmProcessInstanceResultEnum 枚举

    @Schema(description = "用章类型，参见 bpm_oa_type", example = "1")
    private Integer type;

    @Schema(description = "文件名称，模糊匹配", example = "成果报告")
    private String fileName;

    @Schema(description = "原因，模糊匹配", example = "阅读芋道源码")
    private String reason;

    @Schema(description = "对方单位，模糊匹配", example = "规划管理局")
    private String counterpartUnit;

    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    @Schema(description = "申请时间")
    private LocalDateTime[] createTime;

}
