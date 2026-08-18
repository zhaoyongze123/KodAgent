package cn.iocoder.yudao.module.system.dal.dataobject.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("party_file_kod_attachment")
@KeySequence("party_file_kod_attachment_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileKodAttachmentDO extends BaseDO {

    @TableId
    private Long id;

    @TableField("file_id")
    private Long fileId;

    @TableField("kod_source_id")
    private Long kodSourceId;

    @TableField("kod_file_path")
    private String kodFilePath;

    @TableField("kod_parent_path")
    private String kodParentPath;
}
