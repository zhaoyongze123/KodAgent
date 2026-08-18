package cn.iocoder.yudao.server.controller.agent.auth;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Business Agent facade 的服务账号配置。
 */
@Data
@ConfigurationProperties(prefix = "yudao.agent.auth")
public class OaAgentAuthProperties {

    /** 是否启用 facade 认证。 */
    private Boolean enabled = true;
    /** Dify 调用 facade 时携带的固定密钥。 */
    private String apiKey;
    /** 用于访问 OA 业务的服务账号。 */
    private String username;
    /** 用于访问 OA 业务的服务账号密码。 */
    private String password;
    /** 服务账号所属租户。 */
    private Long tenantId = 1L;
    /** 提前刷新 token 的时间，单位为秒。 */
    private long refreshAheadSeconds = 60L;
    /** 外部鉴权头名称。 */
    private String headerName = "X-Agent-Key";
}
