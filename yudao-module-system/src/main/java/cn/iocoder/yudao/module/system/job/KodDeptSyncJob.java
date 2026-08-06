package cn.iocoder.yudao.module.system.job;

import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoProperties;
import cn.iocoder.yudao.module.system.service.auth.KodDeptSyncService;
import cn.iocoder.yudao.framework.tenant.core.util.TenantUtils;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

/**
 * 组织同步定时任务。cron 默认关闭，配置管理员凭据和 cron 后才启用。
 */
@Component
@Slf4j
public class KodDeptSyncJob {

    @Resource
    private KodSsoProperties kodSsoProperties;
    @Resource
    private KodDeptSyncService kodDeptSyncService;

    @Scheduled(cron = "${yudao.kod-sso.organization-sync-cron:-}")
    public void sync() {
        if (!Boolean.TRUE.equals(kodSsoProperties.getOrganizationSyncEnabled())) {
            return;
        }
        try {
            Long tenantId = kodSsoProperties.getTenantId();
            TenantUtils.execute(tenantId, () -> kodDeptSyncService.sync(tenantId));
        } catch (Exception ex) {
            log.error("可道云组织定时同步失败", ex);
        }
    }
}
