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
import java.time.LocalDateTime;

/**
 * OA 项目立项申请 DO
 */
@TableName("bpm_oa_project")
@KeySequence("bpm_oa_project_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOAProjectDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String applicantName;

    private Long deptId;

    private String deptName;

    private String projectName;

    private String projectType;

    private String ownerUnit;

    private String projectSource;

    private Long projectLeaderId;

    private String projectLeaderName;

    private String projectOverview;

    private BigDecimal projectAmount;

    private LocalDateTime plannedStartTime;

    private LocalDateTime plannedEndTime;

    private String participantDeptIds;

    private String participantDeptNames;

    private String riskDescription;

    private String attachmentUrls;

    private String remark;

    /**
     * 枚举 {@link BpmTaskStatusEnum}
     */
    private Integer status;

    private String processInstanceId;

}
