package cn.iocoder.yudao.module.bpm.framework.flowable.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * BPM 的 Flowable 租户策略配置。
 *
 * <p>单租户模式只用于 Flowable 数据。MyBatis Plus 的全局多租户开关仍由
 * {@code yudao.tenant.enable} 独立控制。</p>
 */
@Data
@ConfigurationProperties(prefix = "yudao.bpm")
public class BpmFlowableProperties {

    /** 是否使用固定的 Flowable 租户。 */
    private boolean singleTenantEnabled = true;

    /** 单租户部署使用的 Flowable 租户编号。 */
    private String singleTenantId = "1";

}
