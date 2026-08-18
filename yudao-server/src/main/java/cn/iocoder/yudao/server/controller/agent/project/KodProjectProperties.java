package cn.iocoder.yudao.server.controller.agent.project;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * KodCloud 项目桥接配置。
 *
 * <p>桥接密钥只存在 Java 与 KodCloud 插件进程，不能写入提示词、工具结果或审计日志。</p>
 */
@Data
@ConfigurationProperties(prefix = "yudao.agent.project")
public class KodProjectProperties {

    /** KodCloud 项目插件的只读 Agent 入口。 */
    private String bridgeBaseUrl = "http://127.0.0.1:8001/index.php?plugin/project/agent";
    /** 与 KodCloud 插件配置一致的 HMAC 密钥。 */
    private String bridgeSecret;
    /** 桥接票据有效期，单位秒。 */
    private long ticketTtlSeconds = 60L;
    /** 报告缓存有效期，单位秒。 */
    private long reportTtlSeconds = 86400L;
}
