package cn.iocoder.yudao.module.system.dal.dataobject.notice;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("system_notice_read")
@KeySequence("system_notice_read_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class NoticeReadDO extends BaseDO {

    private Long id;

    private Long noticeId;

    private Long userId;

    private String userNickname;

    private LocalDateTime readTime;
}
