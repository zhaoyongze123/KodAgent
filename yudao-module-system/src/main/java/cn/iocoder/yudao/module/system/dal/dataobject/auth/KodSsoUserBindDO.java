package cn.iocoder.yudao.module.system.dal.dataobject.auth;

import cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO;
import cn.iocoder.yudao.framework.mybatis.core.type.EncryptTypeHandler;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 可道云用户绑定
 */
@TableName(value = "system_kod_sso_user_bind", autoResultMap = true)
@KeySequence("system_kod_sso_user_bind_seq")
@Data
@EqualsAndHashCode(callSuper = true)
public class KodSsoUserBindDO extends TenantBaseDO {

    @TableId
    private Long id;

    /**
     * 本地用户编号
     */
    private Long userId;

    /**
     * 可道云用户唯一标识
     */
    private String kodUserId;

    /**
     * 可道云用户名
     */
    private String kodUsername;

    /**
     * 可道云昵称
     */
    private String kodNickname;

    /**
     * 可道云原始资料
     */
    private String rawProfileJson;

    /**
     * 最近一次 SSO 登录的可道云用户令牌，仅用于后端按用户权限读取可道云文件。
     */
    @TableField(typeHandler = EncryptTypeHandler.class)
    private String kodAccessToken;

}
