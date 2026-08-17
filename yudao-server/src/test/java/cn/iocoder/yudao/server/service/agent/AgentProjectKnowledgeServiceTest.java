package cn.iocoder.yudao.server.service.agent;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AgentProjectKnowledgeServiceTest {

    @Test
    void scheduledSyncDeduplicatesOneProjectAndPrefersAdministrator() {
        Map<AgentProjectKnowledgeService.ProjectSyncKey,
                AgentProjectKnowledgeService.ProjectSyncTarget> targets = new LinkedHashMap<>();

        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 8L, "write");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 3L, "write");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 12L, "admin");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 102L, 3L, "write");

        assertEquals(2, targets.size());
        AgentProjectKnowledgeService.ProjectSyncTarget project101 = targets.get(
                new AgentProjectKnowledgeService.ProjectSyncKey(1L, 101L));
        assertEquals(Long.valueOf(12L), project101.oaUserId);
        assertTrue(project101.administrator);
        assertEquals(Long.valueOf(3L), targets.get(
                new AgentProjectKnowledgeService.ProjectSyncKey(1L, 102L)).oaUserId);
    }

    @Test
    void scheduledSyncUsesSmallestMemberOnlyWhenNoAdministratorExists() {
        Map<AgentProjectKnowledgeService.ProjectSyncKey,
                AgentProjectKnowledgeService.ProjectSyncTarget> targets = new LinkedHashMap<>();

        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 8L, "write");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 3L, "read");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 101L, 5L, "write");
        AgentProjectKnowledgeService.collectScheduledTarget(targets, 1L, 0L, 1L, "admin");

        assertEquals(1, targets.size());
        AgentProjectKnowledgeService.ProjectSyncTarget target = targets.get(
                new AgentProjectKnowledgeService.ProjectSyncKey(1L, 101L));
        assertEquals(Long.valueOf(3L), target.oaUserId);
        assertFalse(target.administrator);
    }

    @Test
    void chineseNaturalQuestionProducesSpecificSearchTerms() {
        List<String> terms = AgentProjectKnowledgeService.keywordTerms("历史建筑保护范围为什么还没有闭合");

        assertTrue(terms.contains("历史建筑保护范围"));
        assertFalse(terms.contains("为什么"));
        assertFalse(terms.contains("没有"));
    }

    @Test
    void planningColloquialQuestionExpandsToAuditableRiskAndResponsibilityTerms() {
        List<String> terms = AgentProjectKnowledgeService.keywordTerms("历史建筑那块为什么还卡着，谁需要跟进？");

        assertTrue(terms.contains("受阻"));
        assertTrue(terms.contains("责任人"));
        assertTrue(terms.contains("下一步"));
    }

    @Test
    void chineseRankingPrefersExactEvidenceOverGenericShortMatch() {
        Map<String, Object> generic = new LinkedHashMap<>();
        generic.put("chunkId", 1L);
        generic.put("ordinal", 0);
        generic.put("name", "项目资料说明");
        generic.put("content", "项目当前仍在推进，后续需要继续核验。");
        generic.put("score", 0D);
        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("chunkId", 2L);
        evidence.put("ordinal", 0);
        evidence.put("name", "更新单元划分与空间设计方案说明");
        evidence.put("content", "老码头片区历史建筑保护范围待技术审查室核验后闭合。");
        evidence.put("score", 0D);

        List<Map<String, Object>> ranked = AgentProjectKnowledgeService.rankCandidates(
                Arrays.asList(generic, evidence),
                AgentProjectKnowledgeService.keywordTerms("历史建筑保护范围为什么还没有闭合"), 2);

        assertEquals(Long.valueOf(2L), ranked.get(0).get("chunkId"));
        assertTrue(((List<?>) ranked.get(0).get("matchedTerms")).contains("历史建筑保护范围"));
    }

    @Test
    void chineseRankingUsesSectionNameBeforeAnOtherwiseEqualChunk() {
        Map<String, Object> generic = new LinkedHashMap<>();
        generic.put("chunkId", 1L);
        generic.put("ordinal", 0);
        generic.put("name", "项目成果汇编");
        generic.put("section", "正文");
        generic.put("content", "本节说明下一阶段工作安排。");
        generic.put("score", 0D);
        Map<String, Object> sectionMatch = new LinkedHashMap<>();
        sectionMatch.put("chunkId", 2L);
        sectionMatch.put("ordinal", 1);
        sectionMatch.put("name", "项目成果汇编");
        sectionMatch.put("section", "交通专题");
        sectionMatch.put("content", "本节说明下一阶段工作安排。");
        sectionMatch.put("score", 0D);

        List<Map<String, Object>> ranked = AgentProjectKnowledgeService.rankCandidates(
                Arrays.asList(generic, sectionMatch), Arrays.asList("交通专题"), 2);

        assertEquals(Long.valueOf(2L), ranked.get(0).get("chunkId"));
    }

    @Test
    void searchNeverReturnsAProjectDocumentWhenItsIndexedVersionIsStale() {
        Map<String, Object> currentProjectFile = new LinkedHashMap<>();
        currentProjectFile.put("sourceType", "PROJECT_FILES");
        currentProjectFile.put("fileId", 21L);
        currentProjectFile.put("contentVersion", "current-hash");
        Map<String, Object> staleProjectFile = new LinkedHashMap<>();
        staleProjectFile.put("sourceType", "PROJECT_FILES");
        staleProjectFile.put("fileId", 22L);
        staleProjectFile.put("contentVersion", "old-hash");
        Map<String, Object> policy = new LinkedHashMap<>();
        policy.put("sourceType", "POLICY_LIBRARY");

        Map<Long, String> visibleVersions = new LinkedHashMap<>();
        visibleVersions.put(21L, "current-hash");
        visibleVersions.put(22L, "new-hash");
        List<Map<String, Object>> current = AgentProjectKnowledgeService.currentSources(
                Arrays.asList(currentProjectFile, staleProjectFile, policy), visibleVersions);

        assertEquals(2, current.size());
        assertTrue(current.contains(currentProjectFile));
        assertFalse(current.contains(staleProjectFile));
        assertTrue(current.contains(policy));
    }

    @Test
    void hybridRankingPromotesSemanticEvidenceWithoutDiscardingExactTitleMatch() {
        Map<String, Object> exactTitle = new LinkedHashMap<>();
        exactTitle.put("chunkId", 1L);
        exactTitle.put("ordinal", 1);
        exactTitle.put("name", "中期成果汇报会准备方案");
        exactTitle.put("content", "汇报材料应在专家咨询会前完成核验。");
        exactTitle.put("score", 5D);
        exactTitle.put("lexicalRank", 1);

        Map<String, Object> semantic = new LinkedHashMap<>();
        semantic.put("chunkId", 2L);
        semantic.put("ordinal", 0);
        semantic.put("name", "专家咨询组织安排");
        semantic.put("content", "会议前需完成成果材料审查和参会单位协调。");
        semantic.put("semanticRank", 1);

        List<Map<String, Object>> ranked = AgentProjectKnowledgeService.mergeHybridCandidates(
                Arrays.asList(exactTitle), Arrays.asList(semantic), 2);

        assertEquals(Long.valueOf(1L), ranked.get(0).get("chunkId"));
        assertEquals("keyword", ranked.get(0).get("retrievalMethod"));
        assertTrue(((Number) ranked.get(1).get("fusionScore")).doubleValue() > 0D);
    }

    @Test
    void evidenceProjectionKeepsOnlyAuditableCitationFields() {
        Map<String, Object> raw = new LinkedHashMap<>();
        raw.put("chunkId", 9L);
        raw.put("name", "综合交通提升规划任务书.docx");
        raw.put("sourceType", "PROJECT_FILES");
        raw.put("projectId", 101L);
        raw.put("fileId", 88L);
        raw.put("contentVersion", "v20260817");
        raw.put("section", "第 3 章 工作内容");
        raw.put("ordinal", 2);
        StringBuilder longContent = new StringBuilder();
        for (int index = 0; index < 20; index++) longContent.append("停车组织与施工期交通保障应形成专项建议。");
        raw.put("content", longContent.toString());
        raw.put("fusionScore", 0.12D);

        Map<String, Object> evidence = AgentProjectKnowledgeService.evidence(raw, 1);

        assertEquals("资料 1", evidence.get("citationId"));
        assertEquals("第 3 章 工作内容", evidence.get("section"));
        assertTrue(String.valueOf(evidence.get("excerpt")).length() <= 280);
        assertFalse(evidence.containsKey("content"));
    }

    @Test
    void embeddingProjectionIsStableAndNormalized() {
        List<Double> full = new ArrayList<>();
        for (int index = 0; index < 4096; index++) full.add((double) ((index % 11) - 5));

        List<Double> first = AgentProjectEmbeddingService.project(full);
        List<Double> second = AgentProjectEmbeddingService.project(full);
        double squaredNorm = 0D;
        for (Double value : first) squaredNorm += value * value;

        assertEquals(1536, first.size());
        assertEquals(first, second);
        assertTrue(Math.abs(1D - squaredNorm) < 0.000001D);
    }

    @Test
    void embeddingProjectionMatchesTheSharedQwenFeatureHashContract() {
        List<Double> projected = AgentProjectEmbeddingService.project(Arrays.asList(1D));

        assertEquals(1D, projected.get(502));
        assertEquals(0D, projected.get(501));
    }

    @Test
    void embeddingBatchResponseUsesOpenAiIndexesInsteadOfResponseOrder() {
        Map<String, Object> second = new LinkedHashMap<>();
        second.put("index", 1);
        second.put("embedding", Arrays.asList(3D, 4D));
        Map<String, Object> first = new LinkedHashMap<>();
        first.put("index", 0);
        first.put("embedding", Arrays.asList(1D, 2D));

        List<List<Double>> vectors = AgentProjectEmbeddingService.decodeEmbeddingVectors(
                Arrays.asList(second, first), 2, 2);

        assertEquals(AgentProjectEmbeddingService.project(Arrays.asList(1D, 2D)), vectors.get(0));
        assertEquals(AgentProjectEmbeddingService.project(Arrays.asList(3D, 4D)), vectors.get(1));
    }

    @Test
    void embeddingClaimOnlyReadsReadySourcesThatHaveNotBeenInvalidated() throws Exception {
        AgentProjectEmbeddingService service = new AgentProjectEmbeddingService();
        ClaimQueryJdbcTemplate jdbcTemplate = new ClaimQueryJdbcTemplate();
        setField(service, "jdbcTemplate", jdbcTemplate);

        service.claimPendingWork();

        assertTrue(jdbcTemplate.lastSql.contains("JOIN agent_knowledge_document"));
        assertTrue(jdbcTemplate.lastSql.contains("JOIN agent_knowledge_source"));
        assertTrue(jdbcTemplate.lastSql.contains("s.extraction_status='READY'"));
        assertTrue(jdbcTemplate.lastSql.contains("s.invalidated_at IS NULL"));
    }

    @Test
    void emptySemanticCandidatesAreUnavailableSoKeywordSearchCanTakeOver() {
        AgentProjectEmbeddingService.SemanticSearch result =
                AgentProjectEmbeddingService.fromSemanticCandidates(Collections.emptyList());

        assertFalse(result.available);
        assertEquals("EMBEDDING_NOT_READY", result.failureCode);
    }

    @Test
    void invalidatingASourceDeletesItsDerivedDocumentsAfterBlockingTheSource() throws Exception {
        AgentProjectKnowledgeService service = new AgentProjectKnowledgeService();
        SqlHistoryJdbcTemplate jdbcTemplate = new SqlHistoryJdbcTemplate();
        setField(service, "jdbcTemplate", jdbcTemplate);

        service.invalidateSource(44L);

        assertEquals(2, jdbcTemplate.sqls.size());
        assertTrue(jdbcTemplate.sqls.get(0).contains("extraction_status='INVALIDATED'"));
        assertTrue(jdbcTemplate.sqls.get(1).startsWith("DELETE FROM agent_knowledge_document"));
    }

    @Test
    void staleProcessingEmbeddingsReturnToThePendingQueue() throws Exception {
        AgentProjectEmbeddingService service = new AgentProjectEmbeddingService();
        RecordingJdbcTemplate jdbcTemplate = new RecordingJdbcTemplate(2);
        setField(service, "jdbcTemplate", jdbcTemplate);
        setField(service, "processingTimeoutMillis", 300_000L);

        int recovered = service.recoverTimedOutProcessing();

        assertEquals(2, recovered);
        assertTrue(jdbcTemplate.sql.contains("status='PROCESSING'"));
        assertTrue(jdbcTemplate.sql.contains("status='PENDING'"));
        assertTrue(jdbcTemplate.sql.contains("updated_at < CURRENT_TIMESTAMP - (? * INTERVAL '1 millisecond')"));
        assertEquals(300_000L, jdbcTemplate.arguments[0]);
    }

    @Test
    void retrievalModeUsesHybridByDefaultAndRejectsUnknownValues() {
        assertEquals(AgentProjectEmbeddingService.RetrievalMode.HYBRID,
                AgentProjectEmbeddingService.parseRetrievalMode(null));
        assertEquals(AgentProjectEmbeddingService.RetrievalMode.KEYWORD,
                AgentProjectEmbeddingService.parseRetrievalMode("keyword"));
        assertEquals(AgentProjectEmbeddingService.RetrievalMode.SEMANTIC,
                AgentProjectEmbeddingService.parseRetrievalMode("semantic"));
        assertEquals(AgentProjectEmbeddingService.RetrievalMode.HYBRID,
                AgentProjectEmbeddingService.parseRetrievalMode("unsupported"));
    }

    @Test
    void vectorRetrievalRemainsDisabledWhenTheOptionalEmbeddingTableIsMissing() throws Exception {
        AgentProjectEmbeddingService service = new AgentProjectEmbeddingService();
        setField(service, "jdbcTemplate", new AvailabilityJdbcTemplate(true, false));
        setField(service, "enabled", true);
        setField(service, "embeddingBaseUrl", "https://embedding.example");
        setField(service, "embeddingApiKey", "secret");

        assertFalse(service.isEnabled());
    }

    @Test
    void vectorRetrievalRequiresTheReadyOnlyHnswIndex() throws Exception {
        AgentProjectEmbeddingService service = new AgentProjectEmbeddingService();
        AvailabilityJdbcTemplate jdbcTemplate = new AvailabilityJdbcTemplate(true, false);
        setField(service, "jdbcTemplate", jdbcTemplate);
        setField(service, "enabled", true);
        setField(service, "embeddingBaseUrl", "https://embedding.example");
        setField(service, "embeddingApiKey", "secret");

        assertFalse(service.isEnabled());
        assertTrue(jdbcTemplate.lastSql.contains("idx_agent_knowledge_embedding_hnsw"));
    }

    @Test
    void retrievalAuditSeparatesEmbeddingFallbackFromAnEmptySearch() {
        Map<String, Object> metadata = AgentProjectKnowledgeService.retrievalAuditMetadata(
                "keyword_fallback", 6, 0, 2, 1, false, "EMBEDDING_TIMEOUT", 27L);

        assertEquals("keyword_fallback", metadata.get("retrievalMode"));
        assertEquals("UNAVAILABLE", metadata.get("vectorState"));
        assertEquals("EMBEDDING_TIMEOUT", metadata.get("vectorFailureCode"));
        assertEquals(27L, metadata.get("elapsedMs"));
    }

    private static void setField(Object target, String name, Object value) throws Exception {
        Field field = target.getClass().getDeclaredField(name);
        field.setAccessible(true);
        field.set(target, value);
    }

    private static final class RecordingJdbcTemplate extends JdbcTemplate {
        private final int affectedRows;
        private String sql;
        private Object[] arguments;

        private RecordingJdbcTemplate(int affectedRows) {
            this.affectedRows = affectedRows;
        }

        @Override
        public int update(String sql, Object... args) {
            this.sql = sql;
            this.arguments = args;
            return affectedRows;
        }
    }

    private static final class AvailabilityJdbcTemplate extends JdbcTemplate {
        private final List<Boolean> answers;
        private String lastSql;

        private AvailabilityJdbcTemplate(Boolean... answers) {
            this.answers = new ArrayList<>(Arrays.asList(answers));
        }

        @Override
        public <T> T queryForObject(String sql, Class<T> requiredType) {
            lastSql = sql;
            return requiredType.cast(answers.remove(0));
        }
    }

    private static final class ClaimQueryJdbcTemplate extends JdbcTemplate {
        private String lastSql = "";

        @Override
        public List<Map<String, Object>> queryForList(String sql, Object... args) {
            lastSql = sql;
            return Collections.emptyList();
        }
    }

    private static final class SqlHistoryJdbcTemplate extends JdbcTemplate {
        private final List<String> sqls = new ArrayList<>();

        @Override
        public int update(String sql, Object... args) {
            sqls.add(sql);
            return 1;
        }
    }
}
