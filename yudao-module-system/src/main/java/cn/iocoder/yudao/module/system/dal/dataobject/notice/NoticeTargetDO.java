package cn.iocoder.yudao.module.system.dal.dataobject.notice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("system_notice_target")
@KeySequence("system_notice_target_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class NoticeTargetDO extends BaseDO {

    @TableId
    private Long id;

    @TableField("notice_id")
    private Long noticeId;

    @TableField("target_type")
    private Integer targetType;

    @TableField("target_id")
    private Long targetId;
}
