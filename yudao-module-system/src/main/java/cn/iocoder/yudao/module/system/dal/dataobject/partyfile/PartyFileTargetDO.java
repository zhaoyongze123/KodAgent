package cn.iocoder.yudao.module.system.dal.dataobject.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("party_file_target")
@KeySequence("party_file_target_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileTargetDO extends BaseDO {

    @TableId
    private Long id;

    @TableField("party_file_id")
    private Long partyFileId;

    @TableField("target_type")
    private Integer targetType;

    @TableField("target_id")
    private Long targetId;
}
