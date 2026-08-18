package cn.iocoder.yudao.module.system.dal.dataobject.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("party_file_read")
@KeySequence("party_file_read_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileReadDO extends BaseDO {

    @TableId
    private Long id;

    @TableField("party_file_id")
    private Long partyFileId;

    @TableField("user_id")
    private Long userId;

    @TableField("user_nickname")
    private String userNickname;

    @TableField("read_time")
    private LocalDateTime readTime;

    @TableField("read_source")
    private Integer readSource;
}
