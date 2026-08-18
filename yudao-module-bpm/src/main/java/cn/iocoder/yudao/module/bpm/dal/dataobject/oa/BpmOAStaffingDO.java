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

import java.time.LocalDateTime;

/**
 * OA 项目人员调配申请 DO
 */
@TableName("bpm_oa_staffing")
@KeySequence("bpm_oa_staffing_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOAStaffingDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String applicantName;

    private Long deptId;

    private String deptName;

    private String projectName;

    private String memberIds;

    private String memberNames;

    private String reason;

    private LocalDateTime transferTime;

    private String expectedWorkPeriod;

    private String targetUnit;

    private String remark;

    /**
     * 枚举 {@link BpmTaskStatusEnum}
     */
    private Integer status;

    private String processInstanceId;

}
