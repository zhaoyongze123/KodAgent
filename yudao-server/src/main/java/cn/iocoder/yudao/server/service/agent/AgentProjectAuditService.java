package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Resource;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 项目 Agent 的最小审计写入服务。
 *
 * <p>只记录用户、项目、快照时间、规则版本、来源版本和错误码，不记录文件正文、
 * KodCloud 路径、下载链接、访问令牌或模型提示词。审计失败不能反向阻断只读业务，
 * 但会由 Java 日志统一记录异常类型，便于运维发现数据库迁移问题。</p>
 */
@Service
public class AgentProjectAuditService {

    private static final String RULE_VERSION = "project-analysis-v1";
    private static final Logger LOGGER = LoggerFactory.getLogger(AgentProjectAuditService.class);

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;

    /**
     * 写入一次项目分析链路审计。
     *
     * @param tenantId 租户编号
     * @param userId 当前 OA 用户编号
     * @param projectId 项目编号
     * @param action ANALYZE、REPORT、SEARCH 或 SYNC
     * @param snapshotEpochSeconds 事实快照时间（Unix 秒），可为空
     * @param sourceVersions 脱敏后的来源版本列表，只允许元数据
     * @param reportId 报告编号；非报告动作传空
     * @param failureCode 结构化失败码；成功时传空
     */
    public void record(Long tenantId, Long userId, long projectId, String action,
                       Long snapshotEpochSeconds, List<Map<String, Object>> sourceVersions,
                       String reportId, String failureCode) {
        try {
            // PostgreSQL JDBC 对 java.time.Instant 的 setObject 支持因版本而异；审计
            // 不能因一个合法的快照时间失效，因此显式转换为驱动稳定支持的 Timestamp。
            Timestamp snapshotAt = snapshotEpochSeconds == null || snapshotEpochSeconds <= 0
                    ? null : Timestamp.from(Instant.ofEpochSecond(snapshotEpochSeconds));
            jdbcTemplate.update("INSERT INTO agent_project_analysis_audit "
                            + "(tenant_id, user_id, project_id, action, snapshot_at, statistics_rule_version, "
                            + "source_versions, report_id, failure_code) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), ?, ?)",
                    tenantId, userId, projectId, action, snapshotAt, RULE_VERSION,
                    JsonUtils.toJsonString(sourceVersions == null ? Collections.emptyList() : sourceVersions),
                    reportId, failureCode);
        } catch (RuntimeException ex) {
            // 审计是旁路能力；不能因为审计表暂时不可用而改变项目查询结果。日志只记录
            // 异常类型，不带 SQL 参数、文件内容、路径、令牌或报告编号。
            LOGGER.warn("项目 Agent 审计写入失败，异常类型={}", ex.getClass().getSimpleName());
        }
    }

    /** 返回当前统计规则版本，供报告和验收日志复用。 */
    public String ruleVersion() {
        return RULE_VERSION;
    }
}
