package cn.iocoder.yudao.server.service.agent;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Startup validator for the externally applied Agent event-store schema.
 *
 * <p>Schema mutation belongs to the deployment boundary only:
 * the canonical files under {@code sql/postgresql/} are run by the local
 * launcher or the Docker migration job before Java starts. Keeping this class read-only
 * prevents a running application from silently owning a second DDL path.</p>
 */
public final class AgentEventSchemaMigrator {

    static final String APPROVAL_CONTRACT_V1 = "agent_approval_confirmation_contract_v1";
    static final String BATCH_APPROVAL_CONTRACT_V1 = "agent_approval_batch_confirmation_contract_v1";
    static final String MEETING_BOOKING_CONTRACT_V1 = "agent_meeting_booking_commit_result_v1";
    static final String PERSONAL_SCHEDULE_CONTRACT_V1 = "agent_personal_schedule_commit_result_v1";
    static final String PARTY_FILE_CONTRACT_V1 = "agent_party_file_commit_result_v1";
    static final String PARTY_FILE_OPERATION_BINDING_V1 = "agent_party_file_operation_binding_v1";
    static final String APPROVAL_OPERATION_BINDING_V1 = "agent_approval_operation_binding_v1";
    static final String MODEL_CONFIG_V1 = "agent_model_config_v1";
    static final String PARTY_KNOWLEDGE_V1 = "agent_party_knowledge_v1";
    static final String PROJECT_PROVIDER_V1 = "agent_project_provider_v1";
    static final String PROJECT_HYBRID_RAG_V1 = "agent_project_hybrid_rag_v1";
    static final String KNOWLEDGE_SOURCE_MANAGEMENT_V1 = "agent_knowledge_source_management_v1";
    static final String DOCUMENT_ARTIFACT_V1 = "agent_generated_artifact_v1";
    private static final String DURABLE_CURSOR_V1 = "agent_run_event_durable_cursor_v1";

    private final JdbcTemplate jdbcTemplate;

    public AgentEventSchemaMigrator(DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }

    /** Fail startup when the canonical deployment migration has not completed. */
    public void migrate() {
        try {
            for (String version : requiredMigrationVersions()) {
                requireMigration(version);
            }
            validateRuntimeContract();
        } catch (DataAccessException ex) {
            throw new IllegalStateException("Agent PostgreSQL schema validation failed; run the canonical Agent "
                    + "PostgreSQL migration set through the deployment migration job before Java starts", ex);
        }
    }

    private void requireMigration(String version) {
        Boolean applied = jdbcTemplate.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM agent_schema_migration WHERE version = ?)",
                Boolean.class, version);
        if (!Boolean.TRUE.equals(applied)) {
            throw new IllegalStateException("Agent PostgreSQL migration " + version
                    + " is missing; Java cannot start before the canonical deployment migration completes");
        }
    }

    /** Verify the fields that the Java approval and schedule services dereference. */
    private void validateRuntimeContract() {
        requireColumn("agent_run", "last_event_cursor");
        requireColumn("agent_run_event", "sequence_no");
        requireColumn("agent_run_event", "archived_at");
        requireColumn("agent_run_event_outbox", "archived_at");
        requireColumn("agent_approval", "draft_type");
        requireColumn("agent_approval", "draft_data");
        requireColumn("agent_approval", "message_id");
        requireColumn("agent_approval", "resume_idempotency_key");
        requireColumn("agent_approval_batch_preview", "decision_idempotency_key");
        requireColumn("agent_approval_batch_preview", "approved_at");
        requireColumn("agent_approval_batch_preview", "rejected_at");
        requireColumn("agent_approval_batch_preview", "rejected_reason");
        requireColumn("agent_approval_batch_preview", "operation_id");
        requireColumn("agent_approval_batch_preview", "result_data");
        requireColumn("agent_meeting_booking_draft", "result_data");
        requireColumn("agent_personal_schedule_draft", "result_data");
        requireColumn("agent_personal_schedule_draft", "operation_id");
        requireColumn("agent_party_file_draft", "result_data");
        requireColumn("agent_party_file_draft", "operation_id");

        requireColumn("agent_model_provider", "base_url");
        requireColumn("agent_model_provider", "deleted");
        requireColumn("agent_model_credential", "api_key_ciphertext");
        requireColumn("agent_model_credential", "status");
        requireColumn("agent_model", "capabilities");
        requireColumn("agent_model", "last_synced_at");
        requireColumn("agent_model_binding", "agent_name");
        requireColumn("agent_model_binding", "enabled");

        requireColumn("knowledge_document", "source_party_file_id");
        requireColumn("knowledge_document", "status");
        requireColumn("knowledge_chunk", "search_vector");
        requireColumn("knowledge_chunk", "status");
        requireColumn("knowledge_fact", "fact_key");
        requireColumn("knowledge_fact", "required_material");
        requireColumn("knowledge_ingest_job", "requested_by_user_id");

        // 项目插件只读 Provider 的持久化状态。项目/任务/文件本身仍位于 KodCloud，
        // 这里只保存用户绑定、索引副本、受控导出和审计，不得替代业务事实源。
        requireColumn("agent_kod_user_binding", "kod_user_id");
        requireColumn("agent_policy_library_binding", "kod_folder_id");
        requireColumn("agent_policy_library_binding", "kod_service_user_id");
        requireColumn("agent_project_report", "analysis_data");
        requireColumn("agent_project_report", "expires_at");
        requireColumn("agent_knowledge_source", "source_type");
        requireColumn("agent_knowledge_source", "extraction_status");
        requireColumn("agent_knowledge_source", "library_id");
        requireColumn("agent_knowledge_library", "source_kind");
        requireColumn("agent_knowledge_library", "access_mode");
        requireColumn("agent_knowledge_library_acl", "subject_type");
        requireColumn("agent_knowledge_upload", "content_data");
        requireColumn("agent_project_document_sync", "status");
        requireColumn("agent_project_analysis_audit", "statistics_rule_version");
        requireColumn("agent_project_analysis_audit", "retrieval_metadata");
        requireColumn("agent_generated_artifact", "content_data");
        requireColumn("agent_generated_artifact", "expires_at");
    }

    private void requireColumn(String tableName, String columnName) {
        Boolean present = jdbcTemplate.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        + "WHERE table_schema = current_schema() AND table_name = ? AND column_name = ?)",
                Boolean.class, tableName, columnName);
        if (!Boolean.TRUE.equals(present)) {
            throw new IllegalStateException("Missing Agent PostgreSQL column " + tableName + "." + columnName);
        }
    }

    static List<String> requiredMigrationVersions() {
        return Collections.unmodifiableList(Arrays.asList(
                DURABLE_CURSOR_V1, APPROVAL_CONTRACT_V1, BATCH_APPROVAL_CONTRACT_V1,
                MEETING_BOOKING_CONTRACT_V1, PERSONAL_SCHEDULE_CONTRACT_V1,
                PARTY_FILE_CONTRACT_V1, PARTY_FILE_OPERATION_BINDING_V1,
                APPROVAL_OPERATION_BINDING_V1,
                MODEL_CONFIG_V1, PARTY_KNOWLEDGE_V1, PROJECT_PROVIDER_V1, PROJECT_HYBRID_RAG_V1,
                KNOWLEDGE_SOURCE_MANAGEMENT_V1,
                DOCUMENT_ARTIFACT_V1));
    }
}
