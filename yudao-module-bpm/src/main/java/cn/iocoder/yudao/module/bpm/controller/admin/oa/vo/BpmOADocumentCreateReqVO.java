package cn.iocoder.yudao.module.bpm.controller.admin.oa.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Schema(description = "管理后台 - 合同/文件审批创建 Request VO")
@Data
public class BpmOADocumentCreateReqVO {

    @Schema(description = "文件类型", requiredMode = Schema.RequiredMode.REQUIRED, example = "合同")
    @NotBlank(message = "文件类型不能为空")
    private String fileType;

    @Schema(description = "文件标题", requiredMode = Schema.RequiredMode.REQUIRED, example = "某项目合同评审")
    @NotBlank(message = "文件标题不能为空")
    private String title;

    @Schema(description = "关联项目", example = "国土空间规划一期")
    private String relatedProject;

    @Schema(description = "对方单位", example = "某规划局")
    private String counterpartUnit;

    @Schema(description = "金额", example = "180000.00")
    private BigDecimal amount;

    @Schema(description = "审批事由", requiredMode = Schema.RequiredMode.REQUIRED, example = "请审批合同签章")
    @NotBlank(message = "审批事由不能为空")
    private String reason;

    @Schema(description = "附件正文地址数组")
    private List<String> attachmentBodyUrls;

    @Schema(description = "附件补充材料地址数组")
    private List<String> attachmentExtraUrls;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "发起人自选审批人 Map", example = "{taskKey1: [1, 2]}")
    private Map<String, List<Long>> startUserSelectAssignees;

}
