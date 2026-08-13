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
 * 显式声明 OA MySQL 的主事务边界。
 *
 * <p>Agent 事件库使用独立、具名的 PostgreSQL 事务管理器；Spring 未指定名称的
 * {@code @Transactional}、Flowable 与 MyBatis 必须继续共用主动态 OA 数据源，
 * 不能意外解析到 Agent 事件库事务管理器。</p>
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
