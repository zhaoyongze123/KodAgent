package cn.iocoder.yudao.module.bpm.dal.dataobject.oa;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * OA 合同/文件审批 DO
 */
@TableName("bpm_oa_document")
@KeySequence("bpm_oa_document_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOADocumentDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String applicantName;

    private Long deptId;

    private String deptName;

    private String fileType;

    private String title;

    private String relatedProject;

    private String counterpartUnit;

    private BigDecimal amount;

    private String reason;

    private String attachmentBodyUrls;

    private String attachmentExtraUrls;

    private String remark;

    /**
     * 枚举 {@link BpmTaskStatusEnum}
     */
    private Integer status;

    private String processInstanceId;

}
