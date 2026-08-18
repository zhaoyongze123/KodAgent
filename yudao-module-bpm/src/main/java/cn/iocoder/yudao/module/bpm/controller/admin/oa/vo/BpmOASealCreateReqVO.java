package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import javax.validation.constraints.NotNull;
import javax.validation.constraints.NotBlank;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - 用章申请创建 Request VO")
@Data
public class BpmOASealCreateReqVO {

    @Schema(description = "使用时间", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "开始时间不能为空")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime startTime;

    @Schema(description = "用章类型-参见 bpm_oa_type 枚举", requiredMode = Schema.RequiredMode.REQUIRED, example = "1")
    @NotNull(message = "用章类型不能为空")
    private Integer type;

    @Schema(description = "文件名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "规划成果报告")
    @NotBlank(message = "文件名称不能为空")
    private String fileName;

    @Schema(description = "文件份数", requiredMode = Schema.RequiredMode.REQUIRED, example = "2")
    @NotNull(message = "文件份数不能为空")
    private Integer fileCount;

    @Schema(description = "用章事由", requiredMode = Schema.RequiredMode.REQUIRED, example = "提交审批归档")
    @NotBlank(message = "用章事由不能为空")
    private String reason;

    @Schema(description = "对方单位", example = "某规划管理局")
    private String counterpartUnit;

    @Schema(description = "是否外带", requiredMode = Schema.RequiredMode.REQUIRED, example = "false")
    @NotNull(message = "是否外带不能为空")
    private Boolean externalCarry;

    @Schema(description = "经办人", requiredMode = Schema.RequiredMode.REQUIRED, example = "张三")
    @NotBlank(message = "经办人不能为空")
    private String operatorName;

    @Schema(description = "附件地址数组")
    private List<String> attachmentUrls;

    @Schema(description = "备注", example = "需当天寄送")
    private String remark;

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

}
