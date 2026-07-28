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

@TableName("party_file")
@KeySequence("party_file_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileDO extends BaseDO {

    @TableId
    private Long id;

    private String title;

    @TableField("category_id")
    private Long categoryId;

    private String summary;

    private String content;

    @TableField("attachment_file_ids")
    private String attachmentFileIds;

    @TableField("storage_type")
    private Integer storageType;

    @TableField("kod_source_id")
    private Long kodSourceId;

    @TableField("kod_folder_path")
    private String kodFolderPath;

    @TableField("kod_folder_name")
    private String kodFolderName;

    private Integer status;

    @TableField("publish_time")
    private LocalDateTime publishTime;
}
