package cn.iocoder.yudao.module.system.dal.dataobject.meetingroom;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 会议室预定参会人 DO
 */
@TableName("system_meeting_booking_attendee")
@KeySequence("system_meeting_booking_attendee_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class MeetingBookingAttendeeDO extends TenantBaseDO {

    @TableId
    private Long id;

    /**
     * 预定编号
     */
    @TableField("booking_id")
    private Long bookingId;

    /**
     * 用户编号
     */
    @TableField("user_id")
    private Long userId;

}
