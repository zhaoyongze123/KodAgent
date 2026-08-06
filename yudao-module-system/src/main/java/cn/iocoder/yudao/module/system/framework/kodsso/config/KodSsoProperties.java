package cn.iocoder.yudao.module.system.framework.kodsso.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;
import java.util.HashSet;
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
     * 后端访问可道云的地址。为空时回退到 baseUrl；生产环境可配置为 Docker 内网地址，
     * 避免业务容器通过宿主机公网地址回环访问仅绑定 127.0.0.1 的可道云端口。
     */
    private String serverBaseUrl;
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

    /**
     * 是否启用可道云组织与部门空间同步。
     */
    private Boolean organizationSyncEnabled = false;

    /**
     * 可道云组织管理员账号。该账号只用于组织同步，不能使用普通用户令牌代替。
     */
    private String organizationSyncUsername;

    /**
     * 可道云组织管理员密码，建议通过环境变量注入。
     */
    private String organizationSyncPassword;

    /**
     * 可道云组织同步管理员令牌。配置后优先使用令牌，不需要每次用密码登录。
     */
    private String organizationSyncAccessToken;

    /**
     * 可道云同步插件地址。为空时使用 baseUrl/index.php?plugin/oaDeptSync/sync。
     */
    private String organizationSyncEndpoint;

    /**
     * 组织同步请求超时时间，单位毫秒。
     */
    private Integer organizationSyncTimeout = 15000;

    /**
     * 可道云根部门编号。
     */
    private String organizationSyncRootGroupId = "1";

    /**
     * 部门空间同步 cron。默认关闭，避免生产环境未配置管理员账号时反复请求。
     */
    private String organizationSyncCron = "-";

}
