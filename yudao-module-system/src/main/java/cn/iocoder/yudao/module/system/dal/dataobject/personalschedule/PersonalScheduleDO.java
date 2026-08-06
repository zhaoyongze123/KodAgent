package cn.iocoder.yudao.module.system.dal.dataobject.personalschedule;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

/**
 * 个人日程 DO
 */
@TableName("system_personal_schedule")
@KeySequence("system_personal_schedule_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class PersonalScheduleDO extends TenantBaseDO {

    @TableId
    private Long id;

    /**
     * 日程标题
     */
    private String title;

    /**
     * 开始时间
     */
    @TableField("start_time")
    private LocalDateTime startTime;

    /**
     * 结束时间
     */
    @TableField("end_time")
    private LocalDateTime endTime;

    /**
     * 所属用户编号
     */
    @TableField("owner_user_id")
    private Long ownerUserId;

    /**
     * 地址
     */
    private String location;

    /**
     * 日程描述
     */
    private String description;

    /**
     * 外部参与者
     */
    @TableField("other_participants")
    private String otherParticipants;

}
