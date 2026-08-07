package cn.iocoder.yudao.server.service.agent;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.OffsetDateTime;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

import cn.iocoder.yudao.module.system.dal.dataobject.personalschedule.PersonalScheduleDO;
import cn.iocoder.yudao.module.system.service.meetingroom.MeetingBookingService;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import cn.iocoder.yudao.module.system.service.personalschedule.PersonalScheduleService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Agent Java/PostgreSQL 契约测试。
 *
 * <p>默认只运行静态契约检查。设置 {@code -Dagent.contract.db=true} 后，
 * 会对本地已执行迁移的 PostgreSQL 运行并发、幂等和租户隔离测试。
 * 设置 {@code -Dagent.business.db=true} 并提供独立 MySQL 连接后，
 * 会验证个人日程业务 Effect 的事务、幂等和三种操作变体。</p>
 */
class AgentPersistenceContractTest {

    @Test
    void sqlContractMustDeclareDurableCursorAndBindingConstraints() throws Exception {
        Path sql = locate("sql/postgresql/agent_run_event.sql");
        String source = new String(Files.readAllBytes(sql), StandardCharsets.UTF_8);
        assertTrue(source.contains("agent_run_event_cursor_seq"));
        assertTrue(source.contains("nextval('agent_run_event_cursor_seq')"));
        assertTrue(source.contains("agent_run_event_durable_cursor_v1"));
        assertTrue(source.contains("uk_agent_run_event_sequence_no"));
        assertTrue(source.contains("CREATE UNIQUE INDEX IF NOT EXISTS uk_agent_run_event_sequence_no"));
        assertTrue(!source.contains("UPDATE agent_run_event SET sequence_no = id"));
        assertTrue(source.contains("uk_agent_approval_pending_draft"));
        assertTrue(source.contains("uk_agent_approval_resume_idempotency"));
        assertTrue(source.contains("tenant_id BIGINT NOT NULL"));
        assertTrue(source.contains("approver_user_id BIGINT NOT NULL"));
        assertTrue(source.contains("idx_agent_run_event_thread_scope_time"));
        assertTrue(source.contains("message_id VARCHAR(128)"));
        assertTrue(source.contains("task_id VARCHAR(128)"));
        assertTrue(source.contains("event_id VARCHAR(128) NOT NULL UNIQUE"));
        assertTrue(source.contains("event_id VARCHAR(128) PRIMARY KEY"));
        assertTrue(source.contains("ALTER TABLE agent_run_event ALTER COLUMN event_id TYPE VARCHAR(128)"));
        assertTrue(source.contains("ALTER TABLE agent_run_event_outbox ALTER COLUMN event_id TYPE VARCHAR(128)"));
        assertTrue(source.contains("last_event_cursor BIGINT NOT NULL DEFAULT 0"));
        assertTrue(source.contains("ALTER TABLE agent_meeting_booking_draft ALTER COLUMN run_id SET NOT NULL"));
        assertTrue(source.contains("ALTER TABLE agent_meeting_booking_draft ALTER COLUMN thread_id SET NOT NULL"));
        assertTrue(source.contains("ALTER TABLE agent_meeting_booking_draft ALTER COLUMN message_id SET NOT NULL"));
        assertTrue(source.contains("ALTER TABLE agent_meeting_booking_draft\n    ADD COLUMN IF NOT EXISTS result_data JSONB"));
        assertTrue(source.contains("agent_meeting_booking_commit_result_v1"));
        assertTrue(source.contains("CREATE TABLE IF NOT EXISTS agent_party_file_draft"));
        assertTrue(source.contains("ALTER TABLE agent_party_file_draft ADD COLUMN IF NOT EXISTS operation_id VARCHAR(128)"));
        assertTrue(source.contains("agent_party_file_operation_binding_v1"));
        assertTrue(source.contains("agent_approval_operation_binding_v1"));
        assertTrue(source.contains("WHERE operation_id IS NULL"));
        assertTrue(source.contains("archived_at = COALESCE(archived_at, CURRENT_TIMESTAMP)"));
        assertTrue(source.contains("status = 'CANCELLED'"));
        assertTrue(source.contains("agent_party_file_commit_result_v1"));
        assertTrue(source.contains("legacy-run:' || draft_id"));
        assertTrue(source.contains("DROP INDEX IF EXISTS uk_agent_draft_idempotency"));
        assertTrue(source.contains("run_id, thread_id, message_id)"));
        assertTrue(source.contains("ALTER COLUMN sequence_no SET NOT NULL"));
        assertTrue(source.contains("setval('agent_run_event_cursor_seq', 1, false)"));
        assertTrue(source.contains("ROW_NUMBER() OVER (PARTITION BY sequence_no ORDER BY id)"));
        assertTrue(source.indexOf("BEGIN;") < source.indexOf("VALUES ('agent_run_event_durable_cursor_v1')"));
        assertTrue(source.indexOf("VALUES ('agent_run_event_durable_cursor_v1')") < source.indexOf("COMMIT;"));

        String eventService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentRunEventService.java")),
                StandardCharsets.UTF_8);
        assertTrue(eventService.contains("hashtextextended(?, 0)"));
        assertTrue(eventService.contains("tenantId + \":\" + userId + \":\" + threadId"));
        assertTrue(eventService.contains("String.valueOf(tenantId)"));
        assertTrue(eventService.contains("String.valueOf(userId)"));
        assertTrue(eventService.contains("last_event_cursor"));
        assertTrue(eventService.contains("run.resumed"));
        assertTrue(eventService.contains("RUN_SCOPE_CONFLICT"));
        assertTrue(eventService.contains("private void lockThread"));
        assertTrue(eventService.contains("threadId"));
        assertTrue(!eventService.contains("pg_advisory_xact_lock(0::bigint)"));
        assertTrue(eventService.contains("narration.upsert"));
        assertTrue(eventService.contains("validateNarration"));
        assertTrue(eventService.contains("NARRATION_ENTRY_CONFLICT"));
        assertTrue(eventService.contains("incomingRevision <= currentRevision"));

        String draftService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentDraftService.java")),
                StandardCharsets.UTF_8);
        assertTrue(draftService.contains("d.approval_id = ?"));
        assertTrue(draftService.contains("a.draft_id = d.draft_id"));
        assertTrue(draftService.contains("a.run_id = d.run_id"));
        assertTrue(draftService.contains("a.thread_id = d.thread_id"));
        assertTrue(draftService.contains("a.message_id = d.message_id"));
        String normalizedDraftService = draftService.replaceAll("\\s+", " ");
        assertTrue(normalizedDraftService.contains(
                "findPendingByIdempotency(Long tenantId, Long userId, String idempotencyKey, "
                        + "String runId, String threadId, String messageId, String operationId)"));
        assertTrue(draftService.contains("hasStoredConflictOverride"));
        assertTrue(draftService.contains("captureSourceMeetingBookingSnapshot"));
        assertTrue(draftService.contains("只能修改或取消由当前用户发起的会议预约"));
        assertTrue(draftService.contains("request.put(\"sourceVersion\""));
        assertFalse(draftService.contains("StringRedisTemplate"));
        assertFalse(draftService.contains("agent:draft:meeting-booking"));

        String approvalService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java")),
                StandardCharsets.UTF_8);
        assertTrue(approvalService.contains("requiredBinding(messageId, \"messageId\")"));
        assertTrue(approvalService.contains("审批与草稿的 run/thread/message 不一致"));
        assertTrue(approvalService.contains("a.tenant_id, a.approver_user_id"));
        assertTrue(approvalService.contains("result.put(\"tenantId\""));
        assertTrue(approvalService.contains("result.put(\"userId\""));

        String schemaMigrator = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentEventSchemaMigrator.java")),
                StandardCharsets.UTF_8);
        assertTrue(schemaMigrator.contains("agent_approval_confirmation_contract_v1"));
        assertTrue(schemaMigrator.contains("agent_approval_batch_confirmation_contract_v1"));
        assertTrue(schemaMigrator.contains("agent_personal_schedule_commit_result_v1"));
        assertTrue(schemaMigrator.contains("agent_meeting_booking_commit_result_v1"));
        assertTrue(schemaMigrator.contains("agent_model_config_v1"));
        assertTrue(schemaMigrator.contains("agent_party_knowledge_v1"));
        assertTrue(schemaMigrator.contains("requireColumn(\"agent_meeting_booking_draft\", \"result_data\")"));
        assertTrue(schemaMigrator.contains("requireMigration"));
        assertTrue(schemaMigrator.contains("validateRuntimeContract"));
        assertTrue(!schemaMigrator.contains("ALTER TABLE"));
        assertTrue(!schemaMigrator.contains("CREATE TABLE"));

        String postgresConfiguration = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentEventPostgresConfiguration.java")),
                StandardCharsets.UTF_8);
        assertTrue(postgresConfiguration.contains("@DependsOn(\"agentEventSchemaMigrator\")"));
        assertTrue(postgresConfiguration.contains("migrator.migrate()"));

        String personalScheduleDraftService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentPersonalScheduleDraftService.java")),
                StandardCharsets.UTF_8);
        assertTrue(!personalScheduleDraftService.contains("void ensureSchema()"));
        assertTrue(!personalScheduleDraftService.contains("ADD COLUMN IF NOT EXISTS result_data"));

        String personalScheduleBusinessCommit = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentPersonalScheduleBusinessCommitService.java")),
                StandardCharsets.UTF_8);
        assertTrue(personalScheduleBusinessCommit.contains("@Transactional(rollbackFor = Exception.class)"));
        assertTrue(personalScheduleBusinessCommit.contains("agent_personal_schedule_effect"));
        assertTrue(personalScheduleBusinessCommit.contains("findByIdempotencyForUpdate"));
        assertTrue(personalScheduleBusinessCommit.contains("PROCESSING"));
        assertTrue(personalScheduleBusinessCommit.contains("SUCCEEDED"));
        assertTrue(personalScheduleBusinessCommit.contains("FOR UPDATE"));
        assertTrue(personalScheduleBusinessCommit.contains("CREATE"));
        assertTrue(personalScheduleBusinessCommit.contains("UPDATE"));
        assertTrue(personalScheduleBusinessCommit.contains("CANCEL"));

        String partyFileDraftService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentPartyFileDraftService.java")),
                StandardCharsets.UTF_8);
        assertTrue(partyFileDraftService.contains("required(request, \"operationId\")"));
        assertTrue(partyFileDraftService.contains("status = 'SUBMITTING'"));
        assertTrue(partyFileDraftService.contains("businessCommitService.findCommittedByDraft"));
        assertTrue(partyFileDraftService.contains("resume_idempotency_key IS NOT NULL"));
        assertFalse(partyFileDraftService.contains("request.get(\"taskId\")"));
        assertFalse(partyFileDraftService.contains("task_id, operation_id"));

        String partyFileBusinessCommit = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentPartyFileBusinessCommitService.java")),
                StandardCharsets.UTF_8);
            assertTrue(partyFileBusinessCommit.contains("agent_party_file_commit"));
            assertTrue(partyFileBusinessCommit.contains("AND approval_id = ? AND operation_id = ?"));
            assertTrue(partyFileBusinessCommit.contains("PARTY_FILE_IDEMPOTENCY_CONFLICT"));
        assertTrue(partyFileBusinessCommit.contains("ON DUPLICATE KEY UPDATE"));
        assertTrue(partyFileBusinessCommit.contains("FOR UPDATE"));
        assertTrue(partyFileBusinessCommit.contains("@Transactional(rollbackFor = Exception.class)"));

        String approvalServiceSource = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java")),
                StandardCharsets.UTF_8);
        assertTrue(approvalServiceSource.contains("LEFT JOIN agent_party_file_draft p"));
        assertTrue(approvalServiceSource.contains("a.archived_at IS NULL AND a.status = 'PENDING'"));
        assertTrue(approvalServiceSource.contains("p.archived_at IS NULL AND a.message_id = p.message_id"));
        assertTrue(approvalServiceSource.contains("COALESCE(d.draft_data, s.draft_data, p.draft_data, a.draft_data)"));
        assertTrue(approvalServiceSource.contains("WHEN p.draft_id IS NOT NULL THEN 'PARTY_FILE'"));

        String personalScheduleBootstrap = new String(Files.readAllBytes(locate(
                "sql/mysql/system-personal-schedule-init.sql")), StandardCharsets.UTF_8);
        assertFalse(personalScheduleBootstrap.contains("agent_personal_schedule_effect"));
        String personalScheduleEffectSchema = new String(Files.readAllBytes(locate(
                "sql/mysql/agent_personal_schedule_effect.sql")), StandardCharsets.UTF_8);
        assertTrue(personalScheduleEffectSchema.contains("agent_schema_migration"));
        assertTrue(personalScheduleEffectSchema.contains("agent_personal_schedule_effect_v1"));
        assertTrue(personalScheduleEffectSchema.contains("uk_agent_personal_schedule_effect_key"));
        assertTrue(personalScheduleEffectSchema.contains("result_data"));

        String mysqlMigration = new String(Files.readAllBytes(locate(
                "scripts/migrate-oa-mysql-schema.sh")), StandardCharsets.UTF_8);
        assertTrue(mysqlMigration.contains("system-personal-schedule-init.sql"));
        assertTrue(mysqlMigration.contains("agent_personal_schedule_effect.sql"));
        assertTrue(mysqlMigration.contains("party-file-kod-schema-v2.sql"));
        assertTrue(mysqlMigration.contains("OA_MYSQL_PASSWORD"));
        assertFalse(mysqlMigration.contains("OA_MYSQL_PASSWORD:-123456"));

        String modelService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentModelService.java")),
                StandardCharsets.UTF_8);
        assertTrue(!modelService.contains("CREATE TABLE IF NOT EXISTS"));
        assertTrue(!modelService.contains("ensureSchema"));
        assertFalse(modelService.contains("XDV71a+xqStEA3WH"));
        assertTrue(modelService.contains("AGENT_MODEL_ENCRYPTION_KEY"));
        assertTrue(modelService.contains("requireEncryptionKey"));

        String localLauncher = new String(Files.readAllBytes(locate("process-compose.yaml")), StandardCharsets.UTF_8);
        assertTrue(localLauncher.contains("./scripts/migrate-agent-event-schema.sh"));

        String localMigration = new String(Files.readAllBytes(locate(
                "scripts/migrate-agent-event-schema.sh")), StandardCharsets.UTF_8);
        assertTrue(localMigration.contains("docker exec -i"));
        assertTrue(localMigration.contains("psql -v ON_ERROR_STOP=1"));
        assertTrue(localMigration.contains("agent_model_config.sql"));
        assertTrue(localMigration.contains("party_knowledge.sql"));
        assertTrue(localMigration.contains("party_knowledge_vector.sql"));
        assertTrue(!localMigration.contains("docker compose"));

        String dockerCompose = new String(Files.readAllBytes(locate(
                "script/docker/docker-compose.yml")), StandardCharsets.UTF_8);
        assertTrue(dockerCompose.contains("agent-event-schema-migrate"));
        assertTrue(dockerCompose.contains("oa-mysql-schema-migrate"));
        assertTrue(dockerCompose.contains("service_completed_successfully"));
        assertTrue(dockerCompose.contains("agent_personal_schedule_effect.sql"));
        assertTrue(dockerCompose.contains("MYSQL_ROOT_PASSWORD must be set"));
        assertTrue(dockerCompose.contains("AGENT_MODEL_ENCRYPTION_KEY must be set"));
        assertTrue(dockerCompose.contains("service_completed_successfully"));
        assertTrue(dockerCompose.contains("agent_run_event.sql}"));
        assertTrue(dockerCompose.contains("agent_model_config.sql"));
        assertTrue(dockerCompose.contains("party_knowledge.sql"));
        assertTrue(dockerCompose.contains("party_knowledge_vector.sql"));
        assertTrue(dockerCompose.contains(":/migrations/agent_run_event.sql:ro"));

        String deploy = new String(Files.readAllBytes(locate("script/docker/deploy.sh")), StandardCharsets.UTF_8);
        assertTrue(deploy.contains("agent_run_event.sql"));
        assertTrue(deploy.contains("agent_personal_schedule_effect.sql"));
        assertTrue(deploy.contains("docker compose run --rm oa-mysql-schema-migrate"));
        assertTrue(deploy.contains("docker compose run --rm agent-event-schema-migrate"));
        String remoteReload = new String(Files.readAllBytes(locate("script/docker/remote-reload-app.sh")), StandardCharsets.UTF_8);
        assertTrue(remoteReload.contains("OA_PERSONAL_SCHEDULE_EFFECT_SCHEMA_SQL_HOST_PATH"));
        assertTrue(remoteReload.contains("docker compose run --rm oa-mysql-schema-migrate"));
        assertTrue(remoteReload.contains("AGENT_MODEL_SCHEMA_SQL_HOST_PATH"));
        assertTrue(remoteReload.contains("AGENT_PARTY_KNOWLEDGE_VECTOR_SCHEMA_SQL_HOST_PATH"));

        String canonicalSchema = new String(Files.readAllBytes(locate(
                "sql/postgresql/agent_run_event.sql")), StandardCharsets.UTF_8);
        assertTrue(canonicalSchema.contains("agent_approval_confirmation_contract_v1"));
        assertTrue(canonicalSchema.contains("agent_approval_batch_confirmation_contract_v1"));
        assertTrue(canonicalSchema.contains("agent_personal_schedule_commit_result_v1"));

        String batchPreviewService = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalBatchPreviewService.java")),
                StandardCharsets.UTF_8);
        assertTrue(batchPreviewService.contains("ON CONFLICT DO NOTHING RETURNING preview_id"));
        assertTrue(batchPreviewService.contains("status = 'EXECUTING'"));
        assertTrue(batchPreviewService.contains("status = 'FAILED'"));
        assertTrue(batchPreviewService.contains("idempotencyKey.equals(current.get(\"idempotencyKey\"))"));
        assertTrue(canonicalSchema.contains("uk_agent_approval_batch_preview_operation"));
        assertTrue(canonicalSchema.contains("'FAILED', 'EXPIRED'"));

        String batchController = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/AgentApprovalToolController.java")),
                StandardCharsets.UTF_8);
        assertTrue(batchController.contains("TransactionSynchronizationManager.registerSynchronization"));
        assertTrue(batchController.contains("public void afterCommit()"));
        assertTrue(batchController.contains("public void afterCompletion(int status)"));
        assertTrue(batchController.contains("status != STATUS_COMMITTED"));

        String batchReconciliation = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalBatchReconciliationService.java")),
                StandardCharsets.UTF_8);
        assertTrue(batchReconciliation.contains("taskService.getHistoricTask(taskId)"));
        assertTrue(batchReconciliation.contains("previewService.complete"));
        assertTrue(batchReconciliation.contains("INCONSISTENT"));
        assertTrue(batchReconciliation.contains("not a child-effect"));

        String modelSchema = new String(Files.readAllBytes(locate(
                "sql/postgresql/agent_model_config.sql")), StandardCharsets.UTF_8);
        assertTrue(modelSchema.contains("agent_model_config_v1"));
        assertTrue(modelSchema.contains("ALTER TABLE agent_model_provider ADD COLUMN IF NOT EXISTS base_url"));
        String partySchema = new String(Files.readAllBytes(locate(
                "sql/postgresql/party_knowledge.sql")), StandardCharsets.UTF_8);
        assertTrue(partySchema.contains("agent_party_knowledge_v1"));
        assertTrue(partySchema.contains("ALTER TABLE knowledge_fact ADD COLUMN IF NOT EXISTS fact_key"));

        String facade = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/OaAgentFacadeController.java")),
                StandardCharsets.UTF_8);
        assertTrue(facade.contains("request.getApprovalId()"));
        assertTrue(facade.contains("findSubmittedMeetingBookingResult"));
        assertTrue(facade.contains("meetingBookingOperation(claimedDraft)"));
        assertTrue(facade.contains("updateMeetingBookingByApplicant"));
        assertTrue(facade.contains("cancelMeetingBookingByApplicant"));
        assertTrue(facade.contains("validateSourceMeetingBookingSnapshot"));
        assertTrue(facade.contains("changedVersion"));
        assertTrue(facade.contains("roomRequest.setId(sourceBookingId)"));
        assertTrue(facade.contains("boolean businessCommitted = false"));
        assertTrue(facade.contains("if (!businessCommitted)"));
        assertTrue(facade.contains("hasStoredConflictOverride(claimedDraft)"));
        assertTrue(!facade.contains("setForceConflict(request.getForceConflict())"));
        assertTrue(draftService.contains("meetingBookingOperation"));
        assertTrue(draftService.contains("findSubmittedMeetingBookingResult"));

        String auth = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/auth/OaAgentAuthInterceptor.java")),
                StandardCharsets.UTF_8);
        assertTrue(auth.contains("mapping.put(\"approval:write\""));
        assertTrue(auth.contains("bpm:task:update"));
        assertTrue(auth.contains("mapping.put(\"schedule:write\""));
        assertTrue(auth.contains("system:personal-schedule:write"));
        assertTrue(auth.contains("X-Agent-Auth-Failure"));
        assertTrue(auth.contains("authFailureReason"));
        assertTrue(auth.contains("permission_denied"));
        assertTrue(auth.contains("HttpStatus.FORBIDDEN"));
    }

    @Test
    void approvalCardMappingMustKeepGenericRequestsOnApprovalContract() throws Exception {
        String source = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java")),
                StandardCharsets.UTF_8);
        assertTrue(source.contains("\"APPROVAL_REQUEST_GENERIC\".equals(draftType)"));
        assertTrue(source.contains("cardType = \"approval_request\""));
        assertTrue(source.indexOf("\"APPROVAL_REQUEST_GENERIC\".equals(draftType)")
                < source.indexOf("\"APPROVAL_WITHDRAW\".equals(draftType)"));
    }

    @Test
    void genericExecutionMustUseResumeProofInsteadOfDecisionIdempotencyKey() throws Exception {
        String source = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java")),
                StandardCharsets.UTF_8);
        int claim = source.indexOf("public Map<String, Object> claimGenericExecution(Long tenantId");
        int update = source.indexOf("UPDATE agent_approval SET status = 'SUBMITTING'", claim);
        assertTrue(update >= 0);
        assertTrue(source.substring(update, source.indexOf("Map<String, Object> current", update))
                .contains("resume_idempotency_key IS NOT NULL"));
        assertFalse(source.substring(update, source.indexOf("Map<String, Object> current", update))
                .contains("AND idempotency_key = ?"));
    }

    @Test
    void resumeRecordMustOnlyWriteTheFirstIdempotencyProof() throws Exception {
        String source = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java")),
                StandardCharsets.UTF_8);
        int method = source.indexOf("public Map<String, Object> recordResume");
        assertTrue(method >= 0);
        int update = source.indexOf("UPDATE agent_approval SET resume_idempotency_key", method);
        assertTrue(update >= 0);
        int end = source.indexOf("Map<String, Object> approval", update);
        assertTrue(end > update);
        String sql = source.substring(update, end);
        assertTrue(sql.contains("resume_idempotency_key IS NULL"));
        assertFalse(sql.contains("AND resume_idempotency_key = ?"));
    }

    @Test
    void approvalRequestAndWithdrawalMustUseDurableTypedFacadeActions() throws Exception {
        Path controllerPath = locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/AgentApprovalToolController.java");
        String controller = new String(Files.readAllBytes(controllerPath), StandardCharsets.UTF_8);
        assertTrue(controller.contains("/approvals/request-draft"));
        assertTrue(controller.contains("/approvals/request-commit"));
        assertTrue(controller.contains("/approvals/withdraw-draft"));
        assertTrue(controller.contains("/approvals/withdraw-commit"));
        assertTrue(controller.contains("/approvals/preview"));
        assertTrue(controller.contains("operationId"));
        assertFalse(controller.contains("/approvals/submit"));
        assertFalse(controller.contains("/tasks/approve"));
        assertFalse(controller.contains("/tasks/reject"));
        assertFalse(controller.contains("ApprovalSubmit"));
        assertFalse(controller.contains("TaskApproveRequest"));
        assertFalse(controller.contains("TaskRejectRequest"));
        assertFalse(controller.contains("TaskActionResponse"));
        assertTrue(controller.contains("formatApprovalTime(normalized.getStartTime())"));
        assertTrue(controller.contains("formatApprovalTime(normalized.getEndTime())"));
        assertTrue(controller.contains("if (value instanceof Number)"));
        String normalizedController = controller.replaceAll("\\s+", " ");
        assertTrue(normalizedController.contains(
                "claimGenericExecution(getTenantId(), getLoginUserId(), approvalId, idempotencyKey, "
                        + "\"APPROVAL_REQUEST\", operationId)"));
        assertTrue(normalizedController.contains(
                "claimGenericExecution(getTenantId(), getLoginUserId(), approvalId, idempotencyKey, "
                        + "\"APPROVAL_WITHDRAW\", operationId)"));
        assertTrue(controller.contains("cancelProcessInstanceByStartUser"));
        assertTrue(controller.contains("instance.getStartUserId()"));

        Path servicePath = locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentApprovalService.java");
        String service = new String(Files.readAllBytes(servicePath), StandardCharsets.UTF_8);
        assertTrue(service.contains("draft_type = ?"));
        assertTrue(service.contains("status = 'SUBMITTING'"));
        assertTrue(service.contains("status = 'COMPLETED'"));
        assertTrue(service.contains("draft_data = draft_data || CAST(? AS jsonb)"));
        assertTrue(service.contains("APPROVAL_REQUEST"));
        assertTrue(service.contains("APPROVAL_WITHDRAW"));
        assertTrue(service.contains("cardType = \"approval_request\""));
        assertTrue(service.contains("cardType = \"approval_withdraw\""));
    }

    @Test
    void singleTaskStatusMustPreserveDurableCompletionAndUnknownBoundaries() throws Exception {
        String controller = new String(Files.readAllBytes(locate(
                "yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/AgentApprovalToolController.java")),
                StandardCharsets.UTF_8);
        int statusMethod = controller.indexOf("getTodoTaskActionStatus");
        assertTrue(statusMethod >= 0);
        String statusSource = controller.substring(statusMethod);
        assertTrue(controller.contains("@GetMapping(\"/tasks/action-status\")"));
        assertTrue(controller.contains("@PostMapping(\"/tasks/action-reconcile\")"));
        assertTrue(statusSource.contains("\"COMPLETED\".equals(approval.get(\"status\"))"));
        assertTrue(statusSource.contains("historicTask.getEndTime() == null"));
        assertTrue(statusSource.contains("rawTaskStatus instanceof Number"));
        assertTrue(statusSource.contains("result.put(\"status\", \"SUBMITTED\")"));
        assertTrue(statusSource.contains("private String optionalString(Object value)"));
        assertFalse(statusSource.contains("String.valueOf(draft.getOrDefault(\"taskId\""));
        assertTrue(controller.contains("completeGenericExecution("));
        assertTrue(controller.contains("status.put(\"approvalStatus\", approval.get(\"status\"))"));
    }

    private static Path locate(String relative) {
        Path direct = Paths.get(System.getProperty("user.dir"), relative);
        return Files.exists(direct) ? direct : Paths.get(System.getProperty("user.dir"), "..", relative);
    }

    @Nested
    @EnabledIfSystemProperty(named = "agent.contract.db", matches = "true")
    class PostgreSqlContractTests {

        private JdbcTemplate jdbcTemplate;
        private TransactionTemplate transactionTemplate;
        private String threadId;

        @BeforeEach
        void setUp() {
            DriverManagerDataSource dataSource = new DriverManagerDataSource(
                    env("AGENT_EVENT_POSTGRES_URL", "jdbc:postgresql://127.0.0.1:15432/langgraph"),
                    env("AGENT_EVENT_POSTGRES_USERNAME", "langgraph"),
                    env("AGENT_EVENT_POSTGRES_PASSWORD", "langgraph"));
            jdbcTemplate = new JdbcTemplate(dataSource);
            transactionTemplate = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
            threadId = "contract-" + UUID.randomUUID();
        }

        @Test
        void concurrentEventsGetDistinctReplayableCursors() throws Exception {
            ExecutorService executor = Executors.newFixedThreadPool(8);
            try {
                List<Callable<Long>> tasks = new ArrayList<>();
                for (int i = 0; i < 8; i++) {
                    final int index = i;
                    tasks.add(() -> transactionTemplate.execute(status -> insertEvent(index)));
                }
                List<Future<Long>> futures = executor.invokeAll(tasks);
                List<Long> cursors = new ArrayList<>();
                for (Future<Long> future : futures) cursors.add(future.get());
                List<Long> distinct = new ArrayList<>(cursors);
                Collections.sort(distinct);
                assertEquals(8, distinct.stream().distinct().count());
                assertEquals(distinct, jdbcTemplate.query(
                        "SELECT sequence_no FROM agent_run_event WHERE thread_id = ? ORDER BY sequence_no",
                        (rs, rowNum) -> rs.getLong(1), threadId));
            } finally {
                executor.shutdownNow();
                cleanup();
            }
        }

        @Test
        void threadScopedLockDoesNotBlockAnotherThread() throws Exception {
            String blockedThreadId = threadId;
            String independentThreadId = "contract-independent-" + UUID.randomUUID();
            java.sql.Connection heldConnection = jdbcTemplate.getDataSource().getConnection();
            heldConnection.setAutoCommit(false);
            try {
                JdbcTemplate heldJdbcTemplate = new JdbcTemplate(
                        new org.springframework.jdbc.datasource.SingleConnectionDataSource(
                                heldConnection, true));
                acquireThreadLock(heldJdbcTemplate, 11L, 21L, blockedThreadId);

                ExecutorService executor = Executors.newSingleThreadExecutor();
                try {
                    Future<Long> independentWrite = executor.submit(() ->
                            transactionTemplate.execute(status -> {
                                acquireThreadLock(jdbcTemplate, 11L, 21L, independentThreadId);
                                return insertEvent(independentThreadId, 11L, 21L,
                                        UUID.randomUUID().toString(), "run-independent", "{}");
                            }));
                    Long cursor = independentWrite.get(2, TimeUnit.SECONDS);
                    assertTrue(cursor > 0);
                    assertEquals(1, jdbcTemplate.queryForObject(
                            "SELECT COUNT(*) FROM agent_run_event WHERE thread_id = ?",
                            Integer.class, independentThreadId));
                } finally {
                    executor.shutdownNow();
                }
            } finally {
                heldConnection.rollback();
                heldConnection.close();
                jdbcTemplate.update("DELETE FROM agent_run_event WHERE thread_id = ?", independentThreadId);
                jdbcTemplate.update("DELETE FROM agent_run WHERE thread_id = ?", independentThreadId);
            }
        }

        @Test
        void sameThreadLockSerializesCursorAllocationUntilCommit() throws Exception {
            java.sql.Connection heldConnection = jdbcTemplate.getDataSource().getConnection();
            heldConnection.setAutoCommit(false);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                JdbcTemplate heldJdbcTemplate = new JdbcTemplate(
                        new org.springframework.jdbc.datasource.SingleConnectionDataSource(
                                heldConnection, true));
                acquireThreadLock(heldJdbcTemplate, 11L, 21L, threadId);
                Long firstCursor = insertEvent(heldJdbcTemplate, threadId, 11L, 21L,
                        UUID.randomUUID().toString(), "run-ordered-1", "{\"index\":1}");

                Future<Long> secondWrite = executor.submit(() ->
                        transactionTemplate.execute(status -> {
                            acquireThreadLock(jdbcTemplate, 11L, 21L, threadId);
                            return insertEvent(jdbcTemplate, threadId, 11L, 21L,
                                    UUID.randomUUID().toString(), "run-ordered-2", "{\"index\":2}");
                        }));

                assertThrows(java.util.concurrent.TimeoutException.class,
                        () -> secondWrite.get(200, TimeUnit.MILLISECONDS));
                heldConnection.commit();
                Long secondCursor = secondWrite.get(2, TimeUnit.SECONDS);
                assertTrue(firstCursor < secondCursor);
            } finally {
                executor.shutdownNow();
                heldConnection.rollback();
                heldConnection.close();
                cleanup();
            }
        }

        @Test
        void eventIdIsIdempotentAndScopeIsTenantUserBound() {
            String eventId = UUID.randomUUID().toString();
            String json = "{\"eventId\":\"" + eventId + "\",\"runId\":\"run-1\"}";
            insertEvent(eventId, "run-1", 11L, 21L, json);
            jdbcTemplate.update("INSERT INTO agent_run_event (event_id, run_id, thread_id, tenant_id, user_id, "
                            + "event_type, event_data, event_time) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP) "
                            + "ON CONFLICT (event_id) DO NOTHING",
                    eventId, "run-1", threadId, "11", "21", "progress", json);
            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_run_event WHERE event_id = ?", Integer.class, eventId));
            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_run_event WHERE tenant_id = ? AND user_id = ? AND thread_id = ?",
                    Integer.class, "11", "21", threadId));
            assertEquals(0, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_run_event WHERE tenant_id = ? AND user_id = ? AND thread_id = ?",
                    Integer.class, "12", "21", threadId));
            cleanup();
        }

        @Test
        void longEventIdsAreAcceptedByFactAndOutboxTables() {
            String eventId = "event-" + repeat('x', 122);
            String json = "{\"eventId\":\"" + eventId + "\",\"runId\":\"run-long-id\","
                    + "\"threadId\":\"" + threadId + "\"}";
            insertEvent(eventId, "run-long-id", 11L, 21L, json);
            jdbcTemplate.update("INSERT INTO agent_run_event_outbox (event_id, stream_key, payload) "
                            + "VALUES (?, ?, CAST(? AS jsonb))", eventId, "agent:events:21:run-long-id", json);

            assertEquals(128, jdbcTemplate.queryForObject(
                    "SELECT character_maximum_length FROM information_schema.columns "
                            + "WHERE table_name = 'agent_run_event' AND column_name = 'event_id'", Integer.class));
            assertEquals(128, jdbcTemplate.queryForObject(
                    "SELECT character_maximum_length FROM information_schema.columns "
                            + "WHERE table_name = 'agent_run_event_outbox' AND column_name = 'event_id'", Integer.class));
            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_run_event_outbox WHERE event_id = ?", Integer.class, eventId));
            cleanup();
        }

        @Test
        void missingDraftMessageIsRejectedBeforePersistence() {
            AgentDraftService service = new AgentDraftService();
            Map<String, Object> request = new LinkedHashMap<>();
            request.put("subject", "context contract");
            request.put("meetingRoomId", 1L);
            request.put("startTime", "2026-07-30 12:00:00");
            request.put("endTime", "2026-07-30 13:00:00");
            request.put("runId", "run-missing-message");
            request.put("threadId", threadId);
            request.put("idempotencyKey", "idem-missing-message");

            assertThrows(RuntimeException.class,
                    () -> service.saveMeetingBookingDraft(11L, 21L, request));
        }

        @Test
        void draftCurrentTurnColumnsAreNotNull() {
            assertEquals(3, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM information_schema.columns "
                            + "WHERE table_name = 'agent_meeting_booking_draft' "
                            + "AND column_name IN ('run_id', 'thread_id', 'message_id') "
                            + "AND is_nullable = 'NO'", Integer.class));
        }

        @Test
        void idempotencyReplayRequiresTheSameRunThreadAndMessage() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String runId = "run-idempotency";
            String messageId = "message-idempotency";
            String idempotencyKey = "idem-context-bound";
            String operationId = "operation-idempotency";
            String json = "{\"draftId\":\"" + draftId + "\",\"runId\":\"" + runId
                    + "\",\"threadId\":\"" + threadId + "\",\"messageId\":\""
                    + messageId + "\",\"operationId\":\"" + operationId + "\"}";
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, tenant_id, owner_user_id, run_id, thread_id, message_id, "
                            + "operation_id, idempotency_key, status, draft_data, expires_at) "
                            + "VALUES (?, 11, 21, ?, ?, ?, ?, ?, 'PENDING', CAST(? AS jsonb), "
                            + "CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, runId, threadId, messageId, operationId, idempotencyKey, json);

            AgentDraftService service = new AgentDraftService();
            Field jdbcField = AgentDraftService.class.getDeclaredField("jdbcTemplate");
            jdbcField.setAccessible(true);
            jdbcField.set(service, jdbcTemplate);
            Method findPending = AgentDraftService.class.getDeclaredMethod(
                    "findPendingByIdempotency", Long.class, Long.class, String.class,
                    String.class, String.class, String.class, String.class);
            findPending.setAccessible(true);

            assertTrue(findPending.invoke(service, 11L, 21L, idempotencyKey,
                    runId, threadId, messageId, operationId) != null);
            assertTrue(findPending.invoke(service, 11L, 21L, idempotencyKey,
                    "run-other", threadId, messageId, operationId) == null);
            assertTrue(findPending.invoke(service, 11L, 21L, idempotencyKey,
                    runId, "thread-other", messageId, operationId) == null);
            assertTrue(findPending.invoke(service, 11L, 21L, idempotencyKey,
                    runId, threadId, "message-other", operationId) == null);
            assertTrue(findPending.invoke(service, 11L, 21L, idempotencyKey,
                    runId, threadId, messageId, "operation-other") == null);
            cleanup();
        }

        @Test
        void approvalAndDraftMessageMismatchCannotBeClaimed() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            String operationId = "op-message-mismatch";
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, operation_id, "
                            + "status, draft_data, expires_at) VALUES (?, ?, 11, 21, 'run-mismatch', ?, "
                            + "'message-draft', ?, 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId, operationId);
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, draft_id, operation_id, "
                            + "status, expires_at) VALUES (?, 11, 21, 'run-mismatch', ?, 'message-approval', ?, ?, "
                            + "'APPROVED', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, draftId, operationId);

            AgentDraftService service = new AgentDraftService();
            Field jdbcField = AgentDraftService.class.getDeclaredField("jdbcTemplate");
            jdbcField.setAccessible(true);
            jdbcField.set(service, jdbcTemplate);
            assertThrows(RuntimeException.class,
                    () -> service.claimMeetingBookingDraft(11L, 21L, draftId, approvalId, operationId));
            assertEquals("PENDING", jdbcTemplate.queryForObject(
                    "SELECT status FROM agent_meeting_booking_draft WHERE draft_id = ?",
                    String.class, draftId));
            cleanup();
        }

        @Test
        void conflictOverrideMustComeFromStoredDraft() {
            AgentDraftService service = new AgentDraftService();
            Map<String, Object> blockedDraft = new LinkedHashMap<>();
            blockedDraft.put("hasConflictOverride", false);
            Map<String, Object> allowedDraft = new LinkedHashMap<>();
            allowedDraft.put("hasConflictOverride", true);

            assertFalse(service.hasStoredConflictOverride(blockedDraft));
            assertTrue(service.hasStoredConflictOverride(allowedDraft));
            assertFalse(service.hasStoredConflictOverride(null));
        }

        @Test
        void runLifecycleStateIsDurableMonotonicAndTerminalIdempotent() throws Exception {
            String runId = "run-lifecycle-" + UUID.randomUUID();
            AgentRunEventService service = new AgentRunEventService();
            Field jdbcField = AgentRunEventService.class.getDeclaredField("jdbcTemplate");
            jdbcField.setAccessible(true);
            jdbcField.set(service, jdbcTemplate);
            Method upsertRun = AgentRunEventService.class.getDeclaredMethod(
                    "upsertRun", Long.class, Long.class, Map.class);
            upsertRun.setAccessible(true);

            applyLifecycleEvent(upsertRun, service, runId, "run.paused", 1L, null);
            assertEquals("PAUSED", runStatus(runId));
            applyLifecycleEvent(upsertRun, service, runId, "run.resumed", 2L, null);
            assertEquals("RUNNING", runStatus(runId));
            applyLifecycleEvent(upsertRun, service, runId, "run.completed", 3L, 300L);
            assertEquals("COMPLETED", runStatus(runId));

            // A duplicate and a late failure must not change the authoritative terminal state.
            applyLifecycleEvent(upsertRun, service, runId, "run.completed", 3L, 300L);
            applyLifecycleEvent(upsertRun, service, runId, "run.failed", 4L, 400L);
            assertEquals("COMPLETED", runStatus(runId));
            assertEquals(4L, jdbcTemplate.queryForObject(
                    "SELECT last_event_cursor FROM agent_run WHERE run_id = ?", Long.class, runId));

            jdbcTemplate.update("DELETE FROM agent_run WHERE run_id = ?", runId);
        }

        @Test
        void approvalBindingRequiresMatchingTenantAndUser() {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, status, draft_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-binding', ?, 'message-1', 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId);
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, task_id, draft_id, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-binding', ?, 'message-1', 'task-1', ?, 'PENDING', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, draftId);
            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_approval a JOIN agent_meeting_booking_draft d ON d.approval_id = a.approval_id "
                            + "WHERE a.approval_id = ? AND a.tenant_id = 11 AND a.approver_user_id = 21 "
                            + "AND a.run_id = d.run_id AND a.thread_id = d.thread_id AND a.message_id = 'message-1' AND a.task_id = 'task-1'",
                    Integer.class, approvalId));
            assertEquals(0, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_approval WHERE approval_id = ? AND tenant_id = 12 AND approver_user_id = 21",
                    Integer.class, approvalId));
            cleanup();
        }

        @Test
        void reconciledTaskCompletionClosesSubmittingApprovalIdempotently() throws Exception {
            String approvalId = UUID.randomUUID().toString();
            String operationId = "op-reconcile-" + UUID.randomUUID();
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, task_id, "
                            + "operation_id, draft_id, draft_type, draft_data, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-reconcile', ?, 'message-reconcile', 'task-reconcile', ?, "
                            + "?, 'APPROVAL_TASK', '{}'::jsonb, 'SUBMITTING', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, operationId, "draft-reconcile-" + UUID.randomUUID());

            AgentApprovalService service = new AgentApprovalService();
            Field field = AgentApprovalService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true);
            result.put("taskId", "task-reconcile");

            Map<String, Object> completed = service.completeGenericExecution(
                    11L, 21L, approvalId, "APPROVAL_TASK", operationId, result);
            assertEquals("COMPLETED", completed.get("status"));
            assertEquals(result, ((Map<?, ?>) completed.get("draft")).get("result"));

            Map<String, Object> replay = service.completeGenericExecution(
                    11L, 21L, approvalId, "APPROVAL_TASK", operationId, result);
            assertEquals("COMPLETED", replay.get("status"));
            assertEquals(result, ((Map<?, ?>) replay.get("draft")).get("result"));
            cleanup();
        }

        @Test
        void resumeReplayMustNotRewriteTheOriginalResumeTimestamp() throws Exception {
            String approvalId = UUID.randomUUID().toString();
            String operationId = "op-resume-" + UUID.randomUUID();
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, "
                            + "operation_id, draft_id, draft_type, draft_data, status, idempotency_key, expires_at) "
                            + "VALUES (?, 11, 21, 'run-resume', ?, 'message-resume', ?, ?, "
                            + "'APPROVAL_TASK', '{}'::jsonb, 'APPROVED', ?, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, operationId, "draft-resume-" + UUID.randomUUID(),
                    "decision-" + UUID.randomUUID());

            AgentApprovalService service = new AgentApprovalService();
            Field field = AgentApprovalService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);

            String resumeKey = "resume-" + UUID.randomUUID();
            Map<String, Object> first = service.recordResume(11L, 21L, approvalId, resumeKey);
            java.sql.Timestamp firstTimestamp = jdbcTemplate.queryForObject(
                    "SELECT resumed_at FROM agent_approval WHERE approval_id = ?",
                    java.sql.Timestamp.class, approvalId);
            Map<String, Object> replay = service.recordResume(11L, 21L, approvalId, resumeKey);
            java.sql.Timestamp replayTimestamp = jdbcTemplate.queryForObject(
                    "SELECT resumed_at FROM agent_approval WHERE approval_id = ?",
                    java.sql.Timestamp.class, approvalId);

            assertEquals(resumeKey, first.get("resumeIdempotencyKey"));
            assertEquals(resumeKey, replay.get("resumeIdempotencyKey"));
            assertEquals(firstTimestamp, replayTimestamp);
            cleanup();
        }

        @Test
        void unexpiredApprovalMustNotCancelItsPendingDraft() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, status, draft_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-expiry', ?, 'message-expiry', 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId);
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, draft_id, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-expiry', ?, 'message-expiry', ?, 'PENDING', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, draftId);

            AgentApprovalService service = new AgentApprovalService();
            java.lang.reflect.Field field = AgentApprovalService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);
            Map<String, Object> approval = service.get(11L, 21L, approvalId);

            assertEquals("PENDING", approval.get("status"));
            assertApprovalContext(approval, 11L, 21L, "run-expiry", threadId, "message-expiry");

            Map<String, Object> pendingCard = service.getPendingCard(11L, 21L, approvalId);
            assertApprovalContext(pendingCard, 11L, 21L, "run-expiry", threadId, "message-expiry");

            Map<String, Object> draftCard = service.getPendingCardByDraft(11L, 21L, draftId);
            assertApprovalContext(draftCard, 11L, 21L, "run-expiry", threadId, "message-expiry");
            assertEquals("PENDING", jdbcTemplate.queryForObject(
                    "SELECT status FROM agent_meeting_booking_draft WHERE draft_id = ?", String.class, draftId));

            String expiredDraftId = UUID.randomUUID().toString();
            String expiredApprovalId = UUID.randomUUID().toString();
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, status, draft_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-expired', ?, 'message-expired', 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    expiredDraftId, expiredApprovalId, threadId);
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, draft_id, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-expired', ?, 'message-expired', ?, 'PENDING', CURRENT_TIMESTAMP - INTERVAL '1 minute')",
                    expiredApprovalId, threadId, expiredDraftId);
            Map<String, Object> expired = service.get(11L, 21L, expiredApprovalId);

            assertEquals("EXPIRED", expired.get("status"));
            assertEquals("CANCELLED", jdbcTemplate.queryForObject(
                    "SELECT status FROM agent_meeting_booking_draft WHERE draft_id = ?", String.class, expiredDraftId));
            cleanup();
        }

        @Test
        void partyFileApprovalCardUsesTheDraftOperationBinding() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            String operationId = "operation-party-card-" + UUID.randomUUID();
            jdbcTemplate.update("INSERT INTO agent_party_file_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, "
                            + "operation_id, idempotency_key, operation, status, draft_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-party-card', ?, 'message-party-card', ?, ?, "
                            + "'CREATE', 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId, operationId,
                    "party-card-" + UUID.randomUUID());
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, "
                            + "operation_id, draft_id, draft_type, draft_data, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-party-card', ?, 'message-party-card', ?, ?, "
                            + "'PARTY_FILE', '{}'::jsonb, 'PENDING', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, operationId, draftId);

            AgentApprovalService service = new AgentApprovalService();
            Field field = AgentApprovalService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);

            Map<String, Object> card = service.getPendingCardByDraft(11L, 21L, draftId);

            assertEquals("PARTY_FILE", card.get("draftType"));
            assertEquals("party_file_approval", card.get("cardType"));
            assertEquals(operationId, card.get("operationId"));
            assertEquals(draftId, card.get("draftId"));
            cleanup();
        }

        @Test
        void partyFileApprovalCompletionIsBoundAndReplayable() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            String operationId = "operation-party-complete-" + UUID.randomUUID();
            jdbcTemplate.update("INSERT INTO agent_party_file_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, "
                            + "operation_id, idempotency_key, operation, status, draft_data, result_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-party-complete', ?, 'message-party-complete', ?, ?, "
                            + "'CREATE', 'SUBMITTED', '{}'::jsonb, CAST(? AS jsonb), CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId, operationId,
                    "party-complete-" + UUID.randomUUID(), "{\"success\":true,\"fileId\":8001}");
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, "
                            + "operation_id, draft_id, draft_type, draft_data, status, resume_idempotency_key, expires_at) "
                            + "VALUES (?, 11, 21, 'run-party-complete', ?, 'message-party-complete', ?, ?, "
                            + "'PARTY_FILE', '{}'::jsonb, 'APPROVED', ?, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, operationId, draftId, "resume-party-complete-" + UUID.randomUUID());

            AgentApprovalService service = new AgentApprovalService();
            Field field = AgentApprovalService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true);
            result.put("fileId", 8001L);

            Map<String, Object> completed = service.completePartyFileExecution(
                    11L, 21L, approvalId, operationId, result);
            assertEquals("COMPLETED", completed.get("status"));
            assertPartyFileResult(result, completed);

            Map<String, Object> replayed = service.completePartyFileExecution(
                    11L, 21L, approvalId, operationId, result);
            assertEquals("COMPLETED", replayed.get("status"));
            assertPartyFileResult(result, replayed);
            cleanup();
        }

        private void assertPartyFileResult(Map<String, Object> expected, Map<String, Object> response) {
            Map<?, ?> actual = (Map<?, ?>) response.get("draft");
            Map<?, ?> actualResult = (Map<?, ?>) actual.get("result");
            assertEquals(expected.get("success"), actualResult.get("success"));
            assertEquals(String.valueOf(expected.get("fileId")), String.valueOf(actualResult.get("fileId")));
        }

        private void assertApprovalContext(Map<String, Object> approval, Long tenantId, Long userId,
                                           String runId, String threadId, String messageId) {
            assertEquals(tenantId, approval.get("tenantId"));
            assertEquals(userId, approval.get("userId"));
            assertEquals(runId, approval.get("runId"));
            assertEquals(threadId, approval.get("threadId"));
            assertEquals(messageId, approval.get("messageId"));
        }

        @Test
        void bookingDraftClaimRequiresExactApprovalAndHasSingleWinner() throws Exception {
            String draftId = UUID.randomUUID().toString();
            String approvalId = UUID.randomUUID().toString();
            String operationId = "op-claim";
            jdbcTemplate.update("INSERT INTO agent_meeting_booking_draft "
                            + "(draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, operation_id, status, draft_data, expires_at) "
                            + "VALUES (?, ?, 11, 21, 'run-claim', ?, 'message-claim', ?, 'PENDING', '{}'::jsonb, CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    draftId, approvalId, threadId, operationId);
            jdbcTemplate.update("INSERT INTO agent_approval "
                            + "(approval_id, tenant_id, approver_user_id, run_id, thread_id, message_id, draft_id, operation_id, status, expires_at) "
                            + "VALUES (?, 11, 21, 'run-claim', ?, 'message-claim', ?, ?, 'APPROVED', CURRENT_TIMESTAMP + INTERVAL '1 hour')",
                    approvalId, threadId, draftId, operationId);

            AgentDraftService service = new AgentDraftService();
            java.lang.reflect.Field field = AgentDraftService.class.getDeclaredField("jdbcTemplate");
            field.setAccessible(true);
            field.set(service, jdbcTemplate);

            assertThrows(RuntimeException.class,
                    () -> service.claimMeetingBookingDraft(11L, 21L, draftId, UUID.randomUUID().toString(), operationId));
            Map<String, Object> claimed = service.claimMeetingBookingDraft(11L, 21L, draftId, approvalId, operationId);
            assertEquals("SUBMITTING", claimed.get("status"));
            assertThrows(RuntimeException.class,
                    () -> service.claimMeetingBookingDraft(11L, 21L, draftId, approvalId, operationId));
            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_meeting_booking_draft WHERE draft_id = ? AND status = 'SUBMITTING'",
                    Integer.class, draftId));
            cleanup();
        }

        private Long insertEvent(int index) {
            acquireThreadLock(jdbcTemplate, 11L, 21L, threadId);
            return insertEvent(threadId, 11L, 21L, UUID.randomUUID().toString(),
                    "run-concurrent", "{\"index\":" + index + "}");
        }

        private Long insertEvent(String eventId, String runId, Long tenantId, Long userId, String json) {
            return insertEvent(jdbcTemplate, threadId, tenantId, userId, eventId, runId, json);
        }

        private Long insertEvent(String targetThreadId, Long tenantId, Long userId,
                                 String eventId, String runId, String json) {
            return insertEvent(jdbcTemplate, targetThreadId, tenantId, userId, eventId, runId, json);
        }

        private Long insertEvent(JdbcTemplate template, String targetThreadId, Long tenantId,
                                 Long userId, String eventId, String runId, String json) {
            return template.queryForObject("INSERT INTO agent_run_event "
                            + "(event_id, run_id, thread_id, tenant_id, user_id, event_type, event_data, event_time) "
                            + "VALUES (?, ?, ?, ?, ?, 'progress', CAST(? AS jsonb), CURRENT_TIMESTAMP) "
                            + "RETURNING sequence_no",
                    Long.class, eventId, runId, targetThreadId, String.valueOf(tenantId),
                    String.valueOf(userId), json);
        }

        private void acquireThreadLock(JdbcTemplate template, Long tenantId, Long userId,
                                       String targetThreadId) {
            String lockScope = tenantId + ":" + userId + ":" + targetThreadId;
            template.query("SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
                    rs -> null, lockScope);
        }

        private void applyLifecycleEvent(Method upsertRun, AgentRunEventService service,
                                         String runId, String type, long cursor, Long durationMs)
                throws Exception {
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("runId", runId);
            event.put("threadId", threadId);
            event.put("messageId", "message-lifecycle");
            event.put("type", type);
            event.put("timestamp", OffsetDateTime.now().toString());
            event.put("sequence", cursor);
            if (durationMs != null) event.put("durationMs", durationMs);
            upsertRun.invoke(service, 21L, 11L, event);
        }

        private String runStatus(String runId) {
            return jdbcTemplate.queryForObject(
                    "SELECT status FROM agent_run WHERE run_id = ?", String.class, runId);
        }

        private String repeat(char value, int count) {
            StringBuilder result = new StringBuilder(count);
            for (int i = 0; i < count; i++) result.append(value);
            return result.toString();
        }

        private void cleanup() {
            jdbcTemplate.update("DELETE FROM agent_party_file_draft WHERE thread_id = ?", threadId);
            jdbcTemplate.update("DELETE FROM agent_approval WHERE thread_id = ?", threadId);
            jdbcTemplate.update("DELETE FROM agent_meeting_booking_draft WHERE thread_id = ?", threadId);
            jdbcTemplate.update("DELETE FROM agent_run_event_outbox WHERE payload ->> 'threadId' = ?", threadId);
            jdbcTemplate.update("DELETE FROM agent_run_event WHERE thread_id = ?", threadId);
            jdbcTemplate.update("DELETE FROM agent_run WHERE thread_id = ?", threadId);
        }

        private String env(String name, String fallback) {
            String value = System.getenv(name);
            return value == null || value.trim().isEmpty() ? fallback : value;
        }
    }

    @Nested
    @EnabledIfSystemProperty(named = "agent.business.db", matches = "true")
    class PersonalScheduleBusinessLedgerTests {

        private final Long tenantId = 900000000L + (long) (Math.random() * 999999L);
        private final Long userId = 910000000L + (long) (Math.random() * 999999L);
        private JdbcTemplate jdbcTemplate;
        private TransactionTemplate transactionTemplate;

        @BeforeEach
        void setUp() {
            DriverManagerDataSource dataSource = new DriverManagerDataSource(
                    requiredEnv("OA_BUSINESS_MYSQL_URL"),
                    requiredEnv("OA_BUSINESS_MYSQL_USERNAME"),
                    requiredEnv("OA_BUSINESS_MYSQL_PASSWORD"));
            jdbcTemplate = new JdbcTemplate(dataSource);
            transactionTemplate = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
            jdbcTemplate.queryForObject("SELECT 1", Integer.class);
        }

        @Test
        void calendarMutationAndEffectLedgerCommitOrRollbackTogether() {
            String draftId = "ledger-atomic-" + UUID.randomUUID();
            String idempotencyKey = "idem-atomic-" + UUID.randomUUID();
            Long scheduleId = transactionTemplate.execute(status -> {
                jdbcTemplate.update("INSERT INTO agent_personal_schedule_effect "
                                + "(tenant_id, owner_user_id, draft_id, idempotency_key, operation, status) "
                                + "VALUES (?, ?, ?, ?, 'CREATE', 'PROCESSING')",
                        tenantId, userId, draftId, idempotencyKey);
                jdbcTemplate.update("INSERT INTO system_personal_schedule "
                                + "(title, start_time, end_time, owner_user_id, tenant_id) "
                                + "VALUES (?, ?, ?, ?, ?)", "ledger atomic", "2030-01-01 10:00:00",
                        "2030-01-01 11:00:00", userId, tenantId);
                Long id = jdbcTemplate.queryForObject("SELECT LAST_INSERT_ID()", Long.class);
                jdbcTemplate.update("UPDATE agent_personal_schedule_effect SET status = 'SUCCEEDED', "
                                + "result_data = JSON_OBJECT('success', true, 'scheduleId', ?) "
                                + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ?",
                        id, tenantId, userId, idempotencyKey);
                return id;
            });

            assertEquals(1, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM system_personal_schedule WHERE id = ? AND tenant_id = ?",
                    Integer.class, scheduleId, tenantId));
            assertEquals("SUCCEEDED", jdbcTemplate.queryForObject(
                    "SELECT status FROM agent_personal_schedule_effect WHERE idempotency_key = ?",
                    String.class, idempotencyKey));

            String rollbackDraft = "ledger-rollback-" + UUID.randomUUID();
            String rollbackKey = "idem-rollback-" + UUID.randomUUID();
            assertThrows(IllegalStateException.class, () -> transactionTemplate.execute(status -> {
                jdbcTemplate.update("INSERT INTO agent_personal_schedule_effect "
                                + "(tenant_id, owner_user_id, draft_id, idempotency_key, operation, status) "
                                + "VALUES (?, ?, ?, ?, 'CREATE', 'PROCESSING')",
                        tenantId, userId, rollbackDraft, rollbackKey);
                jdbcTemplate.update("INSERT INTO system_personal_schedule "
                                + "(title, start_time, end_time, owner_user_id, tenant_id) "
                                + "VALUES (?, ?, ?, ?, ?)", "ledger rollback", "2030-01-02 10:00:00",
                        "2030-01-02 11:00:00", userId, tenantId);
                throw new IllegalStateException("simulate business failure");
            }));
            assertEquals(0, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_personal_schedule_effect WHERE idempotency_key = ?",
                    Integer.class, rollbackKey));
            assertEquals(0, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM system_personal_schedule WHERE title = 'ledger rollback' AND tenant_id = ?",
                    Integer.class, tenantId));
            cleanup();
        }

        @Test
        void businessCommitIsIdempotentAndSupportsCreateUpdateCancel() throws Exception {
            PersonalScheduleService scheduleService = org.mockito.Mockito.mock(PersonalScheduleService.class);
            MeetingBookingService meetingService = org.mockito.Mockito.mock(MeetingBookingService.class);
            org.mockito.Mockito.when(scheduleService.getMyCalendarList(
                    org.mockito.ArgumentMatchers.eq(userId), org.mockito.ArgumentMatchers.any()))
                    .thenReturn(Collections.emptyList());
            org.mockito.Mockito.when(meetingService.getMyCalendarList(
                    org.mockito.ArgumentMatchers.eq(userId), org.mockito.ArgumentMatchers.any(),
                    org.mockito.ArgumentMatchers.any())).thenReturn(Collections.emptyList());
            org.mockito.Mockito.when(scheduleService.createPersonalSchedule(
                    org.mockito.ArgumentMatchers.eq(userId), org.mockito.ArgumentMatchers.any())).thenReturn(7001L);

            AgentPersonalScheduleBusinessCommitService service = new AgentPersonalScheduleBusinessCommitService();
            setField(service, "dataSource", jdbcTemplate.getDataSource());
            setField(service, "personalScheduleService", scheduleService);
            setField(service, "meetingBookingService", meetingService);
            service.initialize();

            Map<String, Object> create = new LinkedHashMap<>();
            create.put("operation", "CREATE");
            create.put("operationId", "operation-create");
            create.put("idempotencyKey", "idem-create-" + UUID.randomUUID());
            create.put("title", "create variant");
            create.put("startTime", "2030-02-01 10:00:00");
            create.put("endTime", "2030-02-01 11:00:00");
            Map<String, Object> created = service.commit(tenantId, userId, "draft-create", create);
            Map<String, Object> replayed = service.commit(tenantId, userId, "draft-create", create);
            assertEquals(created, replayed);
            org.mockito.Mockito.verify(scheduleService, org.mockito.Mockito.times(1))
                    .createPersonalSchedule(org.mockito.ArgumentMatchers.eq(userId), org.mockito.ArgumentMatchers.any());

            LocalDateTime sourceTime = LocalDateTime.of(2030, 2, 2, 10, 0);
            jdbcTemplate.update("INSERT INTO system_personal_schedule "
                            + "(title, start_time, end_time, owner_user_id, tenant_id, update_time) "
                            + "VALUES (?, ?, ?, ?, ?, ?)", "source variant", sourceTime, sourceTime.plusHours(1),
                    userId, tenantId, sourceTime);
            Long sourceId = jdbcTemplate.queryForObject(
                    "SELECT id FROM system_personal_schedule WHERE title = ? AND tenant_id = ? "
                            + "AND owner_user_id = ? ORDER BY id DESC LIMIT 1",
                    Long.class, "source variant", tenantId, userId);
            PersonalScheduleDO source = new PersonalScheduleDO();
            source.setId(sourceId);
            source.setUpdateTime(sourceTime);
            org.mockito.Mockito.when(scheduleService.getPersonalSchedule(userId, sourceId)).thenReturn(source);

            Map<String, Object> update = new LinkedHashMap<>(create);
            update.put("operation", "UPDATE");
            update.put("operationId", "operation-update");
            update.put("idempotencyKey", "idem-update-" + UUID.randomUUID());
            update.put("sourceScheduleId", sourceId);
            update.put("sourceVersion", "2030-02-02 10:00:00");
            service.commit(tenantId, userId, "draft-update", update);
            org.mockito.Mockito.verify(scheduleService, org.mockito.Mockito.times(1))
                    .updatePersonalSchedule(org.mockito.ArgumentMatchers.eq(userId), org.mockito.ArgumentMatchers.any());

            Map<String, Object> cancel = new LinkedHashMap<>();
            cancel.put("operation", "CANCEL");
            cancel.put("operationId", "operation-cancel");
            cancel.put("idempotencyKey", "idem-cancel-" + UUID.randomUUID());
            cancel.put("sourceScheduleId", sourceId);
            cancel.put("sourceVersion", "2030-02-02 10:00:00");
            service.commit(tenantId, userId, "draft-cancel", cancel);
            org.mockito.Mockito.verify(scheduleService, org.mockito.Mockito.times(1))
                    .deletePersonalSchedule(userId, sourceId);
            assertEquals(3, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_personal_schedule_effect WHERE tenant_id = ? AND owner_user_id = ?",
                    Integer.class, tenantId, userId));
            cleanup();
        }

        private void cleanup() {
            jdbcTemplate.update("DELETE FROM agent_personal_schedule_effect WHERE tenant_id = ? AND owner_user_id = ?",
                    tenantId, userId);
            jdbcTemplate.update("DELETE FROM system_personal_schedule WHERE tenant_id = ? AND owner_user_id = ?",
                    tenantId, userId);
        }

        private void setField(Object target, String name, Object value) throws Exception {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        }

        private String requiredEnv(String name) {
            String value = System.getenv(name);
            if (value == null || value.trim().isEmpty()) {
                throw new IllegalStateException(name + " must be set for -Dagent.business.db=true");
            }
            return value;
        }
    }

    @Nested
    @EnabledIfSystemProperty(named = "agent.business.db", matches = "true")
    class PartyFileBusinessLedgerTests {

        private final Long tenantId = 920000000L + (long) (Math.random() * 999999L);
        private final Long userId = 930000000L + (long) (Math.random() * 999999L);
        private JdbcTemplate jdbcTemplate;
        private TransactionTemplate transactionTemplate;

        @BeforeEach
        void setUp() {
            DriverManagerDataSource dataSource = new DriverManagerDataSource(
                    requiredEnv("OA_BUSINESS_MYSQL_URL"),
                    requiredEnv("OA_BUSINESS_MYSQL_USERNAME"),
                    requiredEnv("OA_BUSINESS_MYSQL_PASSWORD"));
            jdbcTemplate = new JdbcTemplate(dataSource);
            transactionTemplate = new TransactionTemplate(new DataSourceTransactionManager(dataSource));
            jdbcTemplate.queryForObject("SELECT 1", Integer.class);
        }

        @Test
        void businessCommitIsIdempotentAcrossCreateUpdateDelete() throws Exception {
            PartyFileService partyFileService = org.mockito.Mockito.mock(PartyFileService.class);
            org.mockito.Mockito.when(partyFileService.createPartyFile(
                    org.mockito.ArgumentMatchers.any())).thenReturn(8001L);

            AgentPartyFileBusinessCommitService service = new AgentPartyFileBusinessCommitService();
            setField(service, "dataSource", jdbcTemplate.getDataSource());
            setField(service, "partyFileService", partyFileService);
            service.initialize();

            Map<String, Object> create = partyDraft("CREATE", "draft-party-create", "approval-party-create");
            Map<String, Object> created = service.commit(tenantId, userId, "draft-party-create", create);
            Map<String, Object> replayed = service.commit(tenantId, userId, "draft-party-create", create);
            assertEquals(created.get("success"), replayed.get("success"));
            assertEquals(String.valueOf(created.get("fileId")), String.valueOf(replayed.get("fileId")));
            assertEquals(created.get("operation"), replayed.get("operation"));
            assertEquals(created.get("message"), replayed.get("message"));
            org.mockito.Mockito.verify(partyFileService, org.mockito.Mockito.times(1))
                    .createPartyFile(org.mockito.ArgumentMatchers.any());

            Map<String, Object> update = partyDraft("UPDATE", "draft-party-update", "approval-party-update");
            update.put("sourcePartyFileId", 8001L);
            service.commit(tenantId, userId, "draft-party-update", update);
            org.mockito.Mockito.verify(partyFileService, org.mockito.Mockito.times(1))
                    .updatePartyFile(org.mockito.ArgumentMatchers.any());

            Map<String, Object> delete = partyDraft("DELETE", "draft-party-delete", "approval-party-delete");
            delete.put("sourcePartyFileId", 8001L);
            service.commit(tenantId, userId, "draft-party-delete", delete);
            org.mockito.Mockito.verify(partyFileService, org.mockito.Mockito.times(1))
                    .deletePartyFile(8001L);

            assertEquals(3, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_party_file_commit WHERE tenant_id = ? AND owner_user_id = ?",
                    Integer.class, tenantId, userId));
        }

        @Test
        void businessFailureRollsBackThePartyFileLedger() throws Exception {
            PartyFileService partyFileService = org.mockito.Mockito.mock(PartyFileService.class);
            org.mockito.Mockito.when(partyFileService.createPartyFile(
                    org.mockito.ArgumentMatchers.any())).thenThrow(new IllegalStateException("simulate OA failure"));

            AgentPartyFileBusinessCommitService service = new AgentPartyFileBusinessCommitService();
            setField(service, "dataSource", jdbcTemplate.getDataSource());
            setField(service, "partyFileService", partyFileService);
            service.initialize();
            Map<String, Object> draft = partyDraft("CREATE", "draft-party-rollback", "approval-party-rollback");

            assertThrows(IllegalStateException.class, () -> transactionTemplate.execute(status -> {
                service.commit(tenantId, userId, "draft-party-rollback", draft);
                return null;
            }));
            assertEquals(0, jdbcTemplate.queryForObject(
                    "SELECT COUNT(*) FROM agent_party_file_commit WHERE tenant_id = ? AND owner_user_id = ?",
                    Integer.class, tenantId, userId));
        }

        private Map<String, Object> partyDraft(String operation, String draftId, String approvalId) {
            Map<String, Object> draft = new LinkedHashMap<>();
            draft.put("operation", operation);
            draft.put("draftId", draftId);
            draft.put("approvalId", approvalId);
            draft.put("operationId", "operation-" + draftId);
            draft.put("idempotencyKey", "idempotency-" + draftId);
            draft.put("title", "Agent 党务文件");
            draft.put("categoryId", 1L);
            draft.put("summary", "集成测试");
            draft.put("content", "测试正文");
            draft.put("storageType", 1);
            draft.put("status", 0);
            draft.put("publishTime", "2030-03-01 10:00:00");
            Map<String, Object> target = new LinkedHashMap<>();
            target.put("targetType", 1);
            draft.put("targets", Collections.singletonList(target));
            return draft;
        }

        @AfterEach
        void cleanup() {
            if (jdbcTemplate != null) {
                jdbcTemplate.update("DELETE FROM agent_party_file_commit WHERE tenant_id = ? AND owner_user_id = ?",
                        tenantId, userId);
            }
        }

        private void setField(Object target, String name, Object value) throws Exception {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        }

        private String requiredEnv(String name) {
            String value = System.getenv(name);
            if (value == null || value.trim().isEmpty()) {
                throw new IllegalStateException(name + " must be set for -Dagent.business.db=true");
            }
            return value;
        }
    }
}
