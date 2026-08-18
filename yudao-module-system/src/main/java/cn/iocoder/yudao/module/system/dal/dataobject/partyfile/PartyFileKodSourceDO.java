package cn.iocoder.yudao.module.system.dal.dataobject.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.framework.mybatis.core.type.EncryptTypeHandler;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName(value = "party_file_kod_source", autoResultMap = true)
@KeySequence("party_file_kod_source_seq")
@Data
@EqualsAndHashCode(callSuper = true)
@TenantIgnore
public class PartyFileKodSourceDO extends BaseDO {

    @TableId
    private Long id;

    private String name;

    @TableField("base_url")
    private String baseUrl;

    @TableField("app_name")
    private String appName;

    @TableField("access_token")
    private String accessToken;

    @TableField("service_username")
    private String serviceUsername;

    @TableField(typeHandler = EncryptTypeHandler.class)
    private String servicePassword;

    @TableField("token_expire_time")
    private LocalDateTime tokenExpireTime;

    @TableField("root_folder_path")
    private String rootFolderPath;

    @TableField("root_folder_name")
    private String rootFolderName;

    private Integer status;

    @TableField("is_default")
    private Boolean isDefault;
}
