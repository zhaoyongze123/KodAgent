package cn.iocoder.yudao.server.controller.agent.project;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/** 启用项目 Provider 的配置属性。 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(KodProjectProperties.class)
public class KodProjectConfiguration {
}
