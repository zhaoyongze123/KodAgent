package cn.iocoder.yudao.server.service.agent;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import javax.sql.DataSource;

/** Agent 事件使用独立 PostgreSQL 数据源，不影响 OA MySQL 业务数据源。 */
@Configuration
@ConditionalOnProperty(
        name = "yudao.agent.events.postgres.enabled",
        havingValue = "true",
        matchIfMissing = true)
public class AgentEventPostgresConfiguration {

    @Bean(name = "agentEventDataSourceProperties")
    @ConfigurationProperties(prefix = "yudao.agent.events.postgres")
    public DataSourceProperties agentEventDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean(name = "agentEventDataSourceHolder")
    public AgentEventDataSourceHolder agentEventDataSourceHolder(
            @Qualifier("agentEventDataSourceProperties") DataSourceProperties properties) {
        return new AgentEventDataSourceHolder(properties.initializeDataSourceBuilder().build());
    }

    @Bean(name = "agentEventJdbcTemplate")
    @DependsOn("agentEventSchemaMigrator")
    public JdbcTemplate agentEventJdbcTemplate(
            @Qualifier("agentEventDataSourceHolder") AgentEventDataSourceHolder holder) {
        // Keep this PostgreSQL connection private to Agent persistence. Exposing
        // a second DataSource bean can make Spring/MyBatis select it as the OA
        // primary datasource, sending system_users queries to PostgreSQL.
        return new JdbcTemplate(holder.dataSource);
    }

    /**
     * Must run before the shared JDBC template is exposed to any Agent service.
     * This makes schema incompatibility a startup failure rather than an
     * intermittent failure while a user is confirming an operation.
     */
    @Bean(name = "agentEventSchemaMigrator")
    public AgentEventSchemaMigrator agentEventSchemaMigrator(
            @Qualifier("agentEventDataSourceHolder") AgentEventDataSourceHolder holder) {
        AgentEventSchemaMigrator migrator = new AgentEventSchemaMigrator(holder.dataSource);
        migrator.migrate();
        return migrator;
    }

    @Bean(name = "agentEventTransactionManager")
    @DependsOn("agentEventSchemaMigrator")
    public PlatformTransactionManager agentEventTransactionManager(
            @Qualifier("agentEventDataSourceHolder") AgentEventDataSourceHolder holder) {
        return new DataSourceTransactionManager(holder.dataSource);
    }

    public static final class AgentEventDataSourceHolder {
        private final DataSource dataSource;

        private AgentEventDataSourceHolder(DataSource dataSource) {
            this.dataSource = dataSource;
        }
    }
}
