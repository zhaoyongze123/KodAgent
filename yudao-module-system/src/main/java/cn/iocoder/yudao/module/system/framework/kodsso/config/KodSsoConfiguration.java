package cn.iocoder.yudao.module.system.framework.kodsso.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * 可道云单点登录配置
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(KodSsoProperties.class)
public class KodSsoConfiguration {
}
