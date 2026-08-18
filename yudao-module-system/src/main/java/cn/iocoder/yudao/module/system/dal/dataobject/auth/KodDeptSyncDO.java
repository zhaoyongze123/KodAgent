package cn.iocoder.yudao.module.system.dal.dataobject.auth;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 可道云部门与本地部门、部门文件空间的稳定映射。
 */
@TableName("system_kod_dept_sync")
@KeySequence("system_kod_dept_sync_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class KodDeptSyncDO extends TenantBaseDO {

    @TableId
    private Long id;

    private String kodGroupId;

    private Long localDeptId;

    private Long kodSourceId;

    private String kodParentGroupId;

    private String groupName;

    private Integer status;

    private String lastSyncStatus;

    private String lastSyncMessage;
}
