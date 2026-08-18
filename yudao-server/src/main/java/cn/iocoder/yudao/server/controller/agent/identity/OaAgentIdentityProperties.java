package cn.iocoder.yudao.server.controller.agent.identity;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Agent 用户身份票据配置。
 */
@Data
@ConfigurationProperties(prefix = "yudao.agent.identity")
public class OaAgentIdentityProperties {

    /** HMAC 签名密钥，生产环境必须独立配置。 */
    private String secret;
    /** 票据有效期，单位为秒。 */
    private long ttlSeconds = 7200L;
    /** Dify 转发票据时使用的请求头。 */
    private String headerName = "X-Agent-Identity";
}
