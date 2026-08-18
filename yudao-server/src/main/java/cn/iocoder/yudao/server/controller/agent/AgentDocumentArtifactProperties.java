package cn.iocoder.yudao.server.controller.agent;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 通用 Agent 附件的存储与下载配置，不依赖任何业务领域。 */
@Data
@ConfigurationProperties(prefix = "yudao.agent.artifact")
public class AgentDocumentArtifactProperties {

    /** 附件受控下载有效期，单位秒。 */
    private long ttlSeconds = 86400L;
}
