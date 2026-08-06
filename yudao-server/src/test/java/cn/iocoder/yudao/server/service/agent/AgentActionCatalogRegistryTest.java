package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.server.controller.agent.AgentActionCatalogController;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentActionCatalogRegistryTest {

    @Test
    void registryExposesUniqueActionsAndConsistentRequiredFields() {
        AgentActionCatalogRegistry registry = new AgentActionCatalogRegistry();
        List<Map<String, Object>> actions = registry.actions();

        assertEquals("agent-actions-v1", registry.contractVersion());
        assertFalse(actions.isEmpty());
        Set<String> actionIds = new HashSet<>();
        for (Map<String, Object> action : actions) {
            String actionId = String.valueOf(action.get("actionId"));
            assertTrue(actionIds.add(actionId), "duplicate action id: " + actionId);
            assertNotNull(action.get("capabilityId"));
            assertNotNull(action.get("executionClass"));
            assertNotNull(action.get("permission"));
            assertNotNull(action.get("fields"));
            assertNotNull(action.get("requiredFields"));
            assertNotNull(action.get("constraints"));

            Set<String> fieldNames = new HashSet<>();
            Set<String> requiredFromFields = new HashSet<>();
            for (Object rawField : (List<?>) action.get("fields")) {
                Map<?, ?> field = (Map<?, ?>) rawField;
                String fieldName = String.valueOf(field.get("name"));
                assertTrue(fieldNames.add(fieldName));
                if (Boolean.TRUE.equals(field.get("required"))) {
                    assertFalse(Boolean.TRUE.equals(field.get("nullable")),
                            actionId + " required field must not be nullable: " + fieldName);
                    requiredFromFields.add(fieldName);
                }
            }
            Set<String> requiredFromContract = new HashSet<>();
            for (Object required : (List<?>) action.get("requiredFields")) {
                String requiredName = String.valueOf(required);
                assertTrue(fieldNames.contains(requiredName),
                        actionId + " requires an unregistered field: " + requiredName);
                assertTrue(requiredFromContract.add(requiredName),
                        actionId + " declares a duplicate required field: " + requiredName);
            }
            assertEquals(requiredFromFields, requiredFromContract,
                    actionId + " requiredFields must exactly match fields.required");
            assertFalse(action.containsKey("tool"));
            assertFalse(action.containsKey("toolName"));
            assertFalse(action.containsKey("path"));
            assertFalse(action.containsKey("url"));
        }
        assertTrue(actionIds.contains("meeting.create"));
        assertTrue(actionIds.contains("schedule.query"));
        assertTrue(actionIds.contains("party_file.create"));

        Map<String, Object> taskAction = actions.stream()
                .filter(item -> "approval.write.task".equals(item.get("actionId")))
                .findFirst().orElseThrow();
        Map<?, ?> decisionField = ((List<Map<String, Object>>) taskAction.get("fields")).stream()
                .filter(field -> "action".equals(field.get("name")))
                .findFirst().orElseThrow();
        assertEquals(List.of("APPROVE", "REJECT"), decisionField.get("enum"));
    }

    @Test
    void controllerKeepsTheExistingHttpResponseContract() {
        AgentActionCatalogRegistry registry = new AgentActionCatalogRegistry();
        Map<String, Object> response = new AgentActionCatalogController(registry).actions();

        assertEquals(registry.contractVersion(), response.get("contractVersion"));
        assertEquals(registry.actions(), response.get("actions"));
    }

    @Test
    void snapshotsDoNotMutateRegistryState() {
        AgentActionCatalogRegistry registry = new AgentActionCatalogRegistry();
        List<Map<String, Object>> first = registry.actions();
        first.get(0).put("description", "tampered");
        ((List<Map<String, Object>>) first.get(0).get("fields")).clear();
        Map<String, Object> firstMeetingCreate = first.stream()
                .filter(item -> "meeting.create".equals(item.get("actionId")))
                .findFirst().orElseThrow();
        ((List<Map<String, Object>>) firstMeetingCreate.get("constraints")).clear();

        List<Map<String, Object>> second = registry.actions();
        assertFalse("tampered".equals(second.get(0).get("description")));
        assertFalse(((List<?>) second.get(0).get("fields")).isEmpty());
        Map<String, Object> meetingCreate = second.stream()
                .filter(item -> "meeting.create".equals(item.get("actionId")))
                .findFirst().orElseThrow();
        assertFalse(((List<?>) meetingCreate.get("constraints")).isEmpty());
    }
}
