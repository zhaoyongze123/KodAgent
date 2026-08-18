package cn.iocoder.yudao.module.system.dal.dataobject.meetingroom;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 会议室 DO
 */
@TableName("system_meeting_room")
@KeySequence("system_meeting_room_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class MeetingRoomDO extends TenantBaseDO {

    @TableId
    private Long id;

    /**
     * 会议室名称
     */
    private String name;

    /**
     * 所在位置
     */
    private String location;

    /**
     * 容量
     */
    private Integer capacity;

    /**
     * 设备配置，逗号分隔
     */
    private String equipment;

    /**
     * 备注
     */
    private String remark;

    /**
     * 状态
     *
     * 枚举 {@link CommonStatusEnum}
     */
    private Integer status;

    /**
     * 排序号
     */
    private Integer sort;

}
