package cn.iocoder.yudao.module.system.framework.kodsso.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/**
 * 可道云单点登录配置
 */
@ConfigurationProperties(prefix = "yudao.kod-sso")
@Data
@Validated
public class KodSsoProperties {

    /**
     * 是否启用
     */
    private Boolean enabled = false;
    /**
     * 可道云根地址，例如 https://kod.example.com/
     */
    private String baseUrl;
    /**
     * 可道云侧 appName
     */
    private String appName = "ruoyi-admin";
    /**
     * 前端回跳地址。为空时 callback 直接返回登录 token
     */
    private String redirectUri;
    /**
     * 后端对外回调根地址。配置后 callback 不再依赖当前请求 host 拼接
     */
    private String callbackBaseUrl;
    /**
     * SSO 登录使用的租户编号
     */
    private Long tenantId = 1L;
    /**
     * 是否允许自动创建本地账号
     */
    private Boolean autoCreateUser = false;
    /**
     * 自动创建的用户名前缀
     */
    private String usernamePrefix = "kod";
    /**
     * 自动创建用户时附加的默认角色
     */
    private Set<Long> defaultRoleIds = new HashSet<>();
    /**
     * 明确的 KodBox 用户到若伊角色映射。key 可以是 KodBox userID 或 name。
     * KodBox 的 apiCheckToken 不返回 OA 角色，不能根据不存在的 roleID 推断权限。
     */
    private Map<String, Long> userRoleMappings = new HashMap<>();
    /**
     * 可道云普通用户角色 ID
     */
    private Long kodCommonRoleId = 1L;
    /**
     * 可道云部门管理员角色 ID
     */
    private Long kodDeptAdminRoleId = 2L;
    /**
     * 可道云超级管理员角色 ID
     */
    private Long kodSuperAdminRoleId = 3L;
    /**
     * 若伊普通用户角色 ID
     */
    private Long localCommonRoleId = 2L;
    /**
     * 若伊部门管理员角色 ID
     */
    private Long localDeptAdminRoleId = 3L;
    /**
     * 若伊超级管理员角色 ID
     */
    private Long localSuperAdminRoleId = 1L;
    /**
     * 换票码有效期
     */
    private Duration exchangeCodeExpire = Duration.ofMinutes(5);

}
