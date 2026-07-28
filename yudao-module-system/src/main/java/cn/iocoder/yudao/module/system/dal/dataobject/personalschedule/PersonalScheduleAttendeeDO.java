package cn.iocoder.yudao.module.system.dal.dataobject.personalschedule;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 个人日程参与人 DO
 */
@TableName("system_personal_schedule_attendee")
@KeySequence("system_personal_schedule_attendee_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class PersonalScheduleAttendeeDO extends TenantBaseDO {

    @TableId
    private Long id;

    /**
     * 日程编号
     */
    @TableField("schedule_id")
    private Long scheduleId;

    /**
     * 用户编号
     */
    @TableField("user_id")
    private Long userId;

}
