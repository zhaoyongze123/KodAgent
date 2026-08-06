package cn.iocoder.yudao.server.service.agent;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentEventSchemaMigratorTest {

    @Test
    void validatorRequiresEveryCanonicalMigrationVersion() {
        assertEquals(9, AgentEventSchemaMigrator.requiredMigrationVersions().size());
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.APPROVAL_CONTRACT_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.BATCH_APPROVAL_CONTRACT_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.PERSONAL_SCHEDULE_CONTRACT_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.MEETING_BOOKING_CONTRACT_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.PARTY_FILE_CONTRACT_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.PARTY_FILE_OPERATION_BINDING_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.MODEL_CONFIG_V1));
        assertTrue(AgentEventSchemaMigrator.requiredMigrationVersions().contains(
                AgentEventSchemaMigrator.PARTY_KNOWLEDGE_V1));
    }
}
