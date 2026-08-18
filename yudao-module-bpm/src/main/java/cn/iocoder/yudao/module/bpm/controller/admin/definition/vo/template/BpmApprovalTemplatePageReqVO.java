package cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Schema(description = "管理后台 - BPM 审批模板分页 Request VO")
@Data
public class BpmApprovalTemplatePageReqVO extends PageParam {

    @Schema(description = "模板名称", example = "请假申请")
    private String name;

    @Schema(description = "流程分类编码", example = "oa_leave")
    private String category;

    @Schema(description = "是否上架", example = "true")
    private Boolean visible;

    @Schema(description = "流程定义标识", example = "oa_leave")
    private String processDefinitionKey;

    @Schema(description = "创建时间")
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime[] createTime;

}
