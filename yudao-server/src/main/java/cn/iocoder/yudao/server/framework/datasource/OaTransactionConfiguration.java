package cn.iocoder.yudao.server.framework.datasource;

import com.baomidou.dynamic.datasource.DynamicRoutingDataSource;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import javax.annotation.Resource;
import javax.sql.DataSource;

/**
 * Makes the OA MySQL transaction boundary explicit.
 *
 * <p>The Agent event store owns a separate, named PostgreSQL transaction
 * manager. Spring's unnamed {@code @Transactional} operations, Flowable and
 * MyBatis must continue to share the primary dynamic OA datasource instead of
 * accidentally resolving the Agent transaction manager.</p>
 */
@Configuration
public class OaTransactionConfiguration {

    @Resource(name = "dataSource")
    private DataSource dataSource;

    @Bean(name = "transactionManager")
    @Primary
    @ConditionalOnMissingBean(name = "transactionManager")
    public PlatformTransactionManager transactionManager() {
        if (!(dataSource instanceof DynamicRoutingDataSource)) {
            throw new IllegalStateException("OA transaction manager requires the primary dynamic datasource");
        }
        return new DataSourceTransactionManager(dataSource);
    }
}
