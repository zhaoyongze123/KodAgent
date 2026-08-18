package cn.iocoder.yudao.module.system.dal.dataobject.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("party_file_category")
@KeySequence("party_file_category_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileCategoryDO extends BaseDO {

    @TableId
    private Long id;

    private String name;

    @TableField("parent_id")
    private Long parentId;

    private Integer sort;

    private Integer status;
}
