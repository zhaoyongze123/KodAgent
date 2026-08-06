package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentPartyFileDraftServiceTest {
    @Test
    void snapshotComparisonUsesPersistedJsonFormForTimeFields() {
        Map<String, Object> current = new LinkedHashMap<>();
        current.put("id", 40L);
        current.put("publishTime", LocalDateTime.of(2026, 8, 5, 14, 0));
        Map<String, Object> persisted = JsonUtils.parseObject(JsonUtils.toJsonString(current), Map.class);
        assertTrue(AgentPartyFileDraftService.sameSnapshot(current, persisted));
    }

    @Test
    void snapshotComparisonIgnoresJsonbMapOrderAndNumberTypes() {
        Map<String, Object> current = new LinkedHashMap<>();
        current.put("title", "验收通知");
        current.put("categoryId", 5L);
        current.put("targets", Arrays.asList(target(2, 1L, "系统管理员"), target(3, 8L, "技术部")));

        Map<String, Object> persisted = new LinkedHashMap<>();
        persisted.put("targets", Arrays.asList(target(2L, 1, "系统管理员"), target(3L, 8, "技术部")));
        persisted.put("categoryId", 5);
        persisted.put("title", "验收通知");

        assertTrue(AgentPartyFileDraftService.sameSnapshot(current, persisted));

        Map<String, Object> changedBusinessValue = new LinkedHashMap<>(persisted);
        changedBusinessValue.put("title", "不同通知");
        assertFalse(AgentPartyFileDraftService.sameSnapshot(current, changedBusinessValue));

        Map<String, Object> changedListOrder = new LinkedHashMap<>(persisted);
        changedListOrder.put("targets", Arrays.asList(target(3L, 8, "技术部"), target(2L, 1, "系统管理员")));
        assertFalse(AgentPartyFileDraftService.sameSnapshot(current, changedListOrder));
    }

    private static Map<String, Object> target(Object targetType, Object targetId, String targetName) {
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("targetType", targetType);
        target.put("targetId", targetId);
        target.put("targetName", targetName);
        return target;
    }

    @Test
    void updateRequestUsesDurableSourceIdInsteadOfModelPayload() {
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("sourcePartyFileId", 999L); // untrusted conversational field
        draft.put("title", "修订通知");
        assertTrue(AgentPartyFileDraftService.asSaveReq(draft, 42L).getId().equals(42L));
        assertTrue(AgentPartyFileDraftService.asSaveReq(draft, null).getId() == null);
    }

    @Test
    void updateMergesSourceTargetsWhenToolSerializesOmittedTargetsAsEmptyList() {
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put("title", "修订通知");
        draft.put("targets", Arrays.asList());
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("targets", Arrays.asList(target(2, 1L, "系统管理员")));

        AgentPartyFileDraftService.mergeUpdateDefaults(draft, source);

        assertEquals(source.get("targets"), draft.get("targets"));
    }
}
