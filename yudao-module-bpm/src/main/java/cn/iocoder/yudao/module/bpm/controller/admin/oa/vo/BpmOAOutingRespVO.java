package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@Schema(description = "管理后台 - 临时外出申请 Response VO")
@Data
public class BpmOAOutingRespVO {

    @Schema(description = "临时外出申请主键", requiredMode = Schema.RequiredMode.REQUIRED, example = "1024")
    private Long id;

    @Schema(description = "外出类型", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer type;

    @Schema(description = "外出日期", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDate outingDate;

    @Schema(description = "外出开始时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime startTime;

    @Schema(description = "外出结束时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime endTime;

    @Schema(description = "外出时长（小时）", requiredMode = Schema.RequiredMode.REQUIRED, example = "2.5")
    private BigDecimal durationHours;

    @Schema(description = "外出地点", example = "市资规局")
    private String destination;

    @Schema(description = "是否离院", example = "true")
    private Boolean outsideOffice;

    @Schema(description = "联系电话", example = "13800000000")
    private String contactMobile;

    @Schema(description = "同行人员", example = "张三、李四")
    private String companionNames;

    @Schema(description = "外出事由", requiredMode = Schema.RequiredMode.REQUIRED, example = "项目现场踏勘")
    private String reason;

    @Schema(description = "备注", example = "预计下午返回")
    private String remark;

    @Schema(description = "申请时间", requiredMode = Schema.RequiredMode.REQUIRED)
    private LocalDateTime createTime;

    @Schema(description = "流程编号")
    private String processInstanceId;

    @Schema(description = "审批结果", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    private Integer status;

}
