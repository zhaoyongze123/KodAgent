package cn.iocoder.yudao.module.bpm.dal.dataobject.definition;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * BPM 审批模板 DO
 *
 * 目的：为 OA 首页提供稳定的“审批模板”对象，和流程定义版本解耦。
 *
 * @author Codex
 */
@TableName("bpm_approval_template")
@KeySequence("bpm_approval_template_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmApprovalTemplateDO extends TenantBaseDO {

    /**
     * 模板编号
     */
    @TableId
    private Long id;
    /**
     * 模板编码
     */
    private String code;
    /**
     * 模板名称
     */
    private String name;
    /**
     * 模板描述
     */
    private String description;
    /**
     * 模板图标
     */
    private String icon;
    /**
     * 流程分类编码
     */
    private String category;
    /**
     * 是否展示在发起审批里
     */
    private Boolean visible;
    /**
     * 排序值
     */
    private Integer sort;
    /**
     * 绑定的流程定义编号
     */
    private String processDefinitionId;
    /**
     * 绑定的流程定义标识
     */
    private String processDefinitionKey;
    /**
     * 绑定的流程模型编号
     */
    private String modelId;

}
