package cn.iocoder.yudao.module.system.enums.permission;

import cn.iocoder.yudao.framework.common.util.object.ObjectUtils;
import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 角色标识枚举
 */
@Getter
@AllArgsConstructor
public enum RoleCodeEnum {

    SUPER_ADMIN("super_admin", "超级管理员"),
    TENANT_ADMIN("tenant_admin", "租户管理员"),
    DEPT_ADMIN("dept_admin", "部门管理员"),
    COMMON_USER("common_user", "普通用户");
    ;

    /**
     * 角色编码
     */
    private final String code;
    /**
     * 名字
     */
    private final String name;

    public static boolean isSuperAdmin(String code) {
        return ObjectUtils.equalsAny(code, SUPER_ADMIN.getCode());
    }

}
