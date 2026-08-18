package cn.iocoder.yudao.server.service.agent;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 项目资料的异步向量索引与语义候选召回。
 *
 * <p>本服务只操作已经由 {@link AgentProjectKnowledgeService} 提取的派生文本。它既不
 * 读取 KodCloud 文件，也不判断项目权限；调用方必须先把查询限制在本轮已授权的
 * source_id 集合内。embedding 服务不可用时返回结构化降级状态，不影响全文检索。</p>
 */
@Service
public class AgentProjectEmbeddingService {

    static final int PROJECTED_DIMENSIONS = 1536;
    private static final int DEFAULT_SOURCE_DIMENSIONS = 4096;
    private static final int MAX_RETRIES = 5;

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Value("${OA_AGENT_PROJECT_RAG_ENABLED:${yudao.agent.project.rag.enabled:false}}")
    private boolean enabled;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_BASE_URL:${yudao.agent.project.rag.embedding-base-url:}}")
    private String embeddingBaseUrl;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_API_KEY:${yudao.agent.project.rag.embedding-api-key:}}")
    private String embeddingApiKey;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_MODEL:${yudao.agent.project.rag.embedding-model:Qwen/Qwen3-VL-Embedding-8B}}")
    private String embeddingModel;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_DIMENSIONS:${yudao.agent.project.rag.embedding-dimensions:4096}}")
    private int sourceDimensions;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_TIMEOUT_MS:${yudao.agent.project.rag.embedding-timeout-ms:5000}}")
    private long timeoutMillis;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_BATCH_SIZE:${yudao.agent.project.rag.embedding-batch-size:16}}")
    private int batchSize;
    @Value("${OA_AGENT_PROJECT_EMBEDDING_PROCESSING_TIMEOUT_MS:${yudao.agent.project.rag.embedding-processing-timeout-ms:300000}}")
    private long processingTimeoutMillis;
    @Value("${OA_AGENT_PROJECT_RAG_RETRIEVAL_MODE:${yudao.agent.project.rag.retrieval-mode:hybrid}}")
    private String configuredRetrievalMode;

    private volatile Boolean pgVectorAvailable;
    private volatile Boolean embeddingStorageAvailable;

    /** 定时补齐已有资料的 embedding，并重试暂时失败的任务。 */
    @Scheduled(fixedDelayString = "${yudao.agent.project.rag.embedding-worker-interval-ms:60000}")
    public void processPendingEmbeddings() {
        if (!isEnabled()) return;
        recoverTimedOutProcessing();
        ensureQueuedChunks();
        List<EmbeddingWork> work = claimPendingWork();
        // 来源可能在领取和 HTTP 请求之间失权；发送前再用数据库事实源复核一次，
        // 避免把已删除或已失效的资料外发给 embedding 服务。
        work = revalidateWork(work);
        if (work.isEmpty()) return;
        try {
            List<String> inputs = new ArrayList<>();
            for (EmbeddingWork item : work) inputs.add(item.content);
            List<List<Double>> vectors = queryEmbeddings(inputs);
            for (int index = 0; index < work.size(); index++) {
                EmbeddingWork item = work.get(index);
                updateReady(item.chunkId, item.contentHash, vectors.get(index));
            }
        } catch (RuntimeException ex) {
            for (EmbeddingWork item : work) updateFailure(item.chunkId, safeError(ex));
        }
    }

    /**
     * 在已完成权限过滤的 source 范围内执行向量召回。
     *
     * <p>返回的 {@code available=false} 表示调用方应继续使用全文检索。索引表存在
     * 但当前没有 READY 向量时也视为不可用，避免 semantic 模式把“尚未完成索引”
     * 错误地返回为空结果。</p>
     */
    SemanticSearch semanticCandidates(List<Object> sourceIds, String query, int limit) {
        if (!isEnabled()) return SemanticSearch.unavailable("RAG_DISABLED");
        if (sourceIds == null || sourceIds.isEmpty()) return SemanticSearch.available(Collections.emptyList());
        try {
            List<Double> vector = queryEmbedding(query);
            String placeholders = String.join(",", Collections.nCopies(sourceIds.size(), "?"));
            String vectorLiteral = vectorLiteral(vector);
            String sql = "SELECT c.chunk_id, d.source_id, s.source_type, s.project_id, s.kod_file_id, s.library_id, "
                    + "s.display_name, s.document_type, s.content_version, c.section, c.ordinal, c.content, "
                    + "1 - (e.embedding_projected <=> CAST(? AS vector)) semantic_score "
                    + "FROM agent_knowledge_chunk_embedding e "
                    + "JOIN agent_knowledge_chunk c ON c.chunk_id=e.chunk_id "
                    + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                    + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                    + "WHERE e.status='READY' AND e.embedding_projected IS NOT NULL "
                    + "AND e.embedding_model=? AND s.extraction_status='READY' "
                    + "AND s.source_id IN (" + placeholders + ") AND s.invalidated_at IS NULL "
                    + "ORDER BY e.embedding_projected <=> CAST(? AS vector) ASC LIMIT ?";
            List<Object> args = new ArrayList<>();
            args.add(vectorLiteral);
            args.add(modelKey());
            args.addAll(sourceIds);
            args.add(vectorLiteral);
            args.add(Math.min(30, Math.max(1, limit)));
            List<Map<String, Object>> rows = jdbcTemplate.query(sql,
                    (rs, rowNum) -> semanticCandidate(rs, rowNum + 1), args.toArray());
            return fromSemanticCandidates(rows);
        } catch (RuntimeException ex) {
            return SemanticSearch.unavailable(safeError(ex));
        }
    }

    /** 语义候选必须保留库标识，后续才能用“库 + 文件 + 版本”复核 KodCloud 权限。 */
    static Map<String, Object> semanticCandidate(ResultSet rs, int rank) throws SQLException {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("chunkId", rs.getLong("chunk_id"));
        item.put("sourceId", rs.getLong("source_id"));
        item.put("sourceType", rs.getString("source_type"));
        item.put("projectId", rs.getObject("project_id"));
        item.put("fileId", rs.getObject("kod_file_id"));
        item.put("libraryId", rs.getObject("library_id"));
        item.put("name", rs.getString("display_name"));
        item.put("documentType", rs.getString("document_type"));
        item.put("contentVersion", rs.getString("content_version"));
        item.put("section", rs.getString("section"));
        item.put("ordinal", rs.getInt("ordinal"));
        item.put("content", rs.getString("content"));
        item.put("semanticScore", rs.getDouble("semantic_score"));
        item.put("semanticRank", rank);
        return item;
    }

    boolean isEnabled() {
        return enabled && StringUtils.hasText(embeddingBaseUrl) && StringUtils.hasText(embeddingApiKey)
                && pgVectorAvailable() && embeddingStorageAvailable();
    }

    /** 配置开关本身，用于区分“主动关闭”与“已开启但 embedding 不可用”的降级审计。 */
    boolean isRagRequested() {
        return enabled;
    }

    RetrievalMode retrievalMode() {
        return parseRetrievalMode(configuredRetrievalMode);
    }

    static RetrievalMode parseRetrievalMode(String value) {
        if (!StringUtils.hasText(value)) return RetrievalMode.HYBRID;
        try {
            return RetrievalMode.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ignored) {
            return RetrievalMode.HYBRID;
        }
    }

    @SuppressWarnings("unchecked")
    static SemanticSearch fromSemanticCandidates(List<?> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return SemanticSearch.unavailable("EMBEDDING_NOT_READY");
        }
        return SemanticSearch.available((List<Map<String, Object>>) (List<?>) candidates);
    }

    private boolean pgVectorAvailable() {
        Boolean known = pgVectorAvailable;
        if (Boolean.TRUE.equals(known)) return true;
        try {
            Boolean available = jdbcTemplate.queryForObject(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')", Boolean.class);
            if (Boolean.TRUE.equals(available)) pgVectorAvailable = Boolean.TRUE;
            return Boolean.TRUE.equals(available);
        } catch (RuntimeException ex) {
            return false;
        }
    }

    /**
     * pgvector 扩展可由运维预先安装，但当前数据库账号未必有权限创建本模块的表和
     * READY 向量索引。只有两者均可用时才启动 worker，避免全文检索可用时定时任务
     * 反复写错误日志，或在资料量增长后退化为未受限的顺序向量扫描。
     */
    private boolean embeddingStorageAvailable() {
        Boolean known = embeddingStorageAvailable;
        if (Boolean.TRUE.equals(known)) return true;
        try {
            Boolean available = jdbcTemplate.queryForObject(
                    "SELECT to_regclass('agent_knowledge_chunk_embedding') IS NOT NULL "
                            + "AND to_regclass('idx_agent_knowledge_embedding_hnsw') IS NOT NULL", Boolean.class);
            if (Boolean.TRUE.equals(available)) embeddingStorageAvailable = Boolean.TRUE;
            return Boolean.TRUE.equals(available);
        } catch (RuntimeException ex) {
            return false;
        }
    }

    private void ensureQueuedChunks() {
        String currentModel = modelKey();
        // 兼容旧版本已经标记失效但尚未级联清理的记录，先清掉其 embedding，
        // 防止 worker 继续持有不可见资料的待处理任务。
        jdbcTemplate.update("DELETE FROM agent_knowledge_chunk_embedding e "
                + "USING agent_knowledge_chunk c, agent_knowledge_document d, agent_knowledge_source s "
                + "WHERE e.chunk_id=c.chunk_id AND c.document_id=d.document_id AND d.source_id=s.source_id "
                + "AND (s.invalidated_at IS NOT NULL OR s.extraction_status<>'READY')");
        jdbcTemplate.update("INSERT INTO agent_knowledge_chunk_embedding "
                        + "(chunk_id, content_hash, embedding_model, status, attempt_count, next_retry_at) "
                        + "SELECT c.chunk_id, c.content_hash, ?, 'PENDING', 0, CURRENT_TIMESTAMP "
                        + "FROM agent_knowledge_chunk c JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                        + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                        + "WHERE s.extraction_status='READY' AND s.invalidated_at IS NULL "
                        + "ON CONFLICT (chunk_id) DO NOTHING", currentModel);
        jdbcTemplate.update("UPDATE agent_knowledge_chunk_embedding e SET content_hash=c.content_hash, "
                        + "embedding_model=?, embedding_projected=NULL, status='PENDING', attempt_count=0, "
                        + "next_retry_at=CURRENT_TIMESTAMP, last_error_code=NULL, updated_at=CURRENT_TIMESTAMP "
                        + "FROM agent_knowledge_chunk c WHERE e.chunk_id=c.chunk_id "
                        + "AND (e.content_hash<>c.content_hash OR e.embedding_model<>?)",
                currentModel, currentModel);
    }

    List<EmbeddingWork> claimPendingWork() {
        int limit = Math.min(64, Math.max(1, batchSize));
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                "SELECT e.chunk_id, e.content_hash, c.content FROM agent_knowledge_chunk_embedding e "
                        + "JOIN agent_knowledge_chunk c ON c.chunk_id=e.chunk_id "
                        + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                        + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                        + "WHERE e.status='PENDING' AND e.next_retry_at<=CURRENT_TIMESTAMP "
                        + "AND d.extraction_status='READY' AND s.extraction_status='READY' "
                        + "AND s.invalidated_at IS NULL "
                        + "ORDER BY e.updated_at ASC, e.chunk_id ASC LIMIT ?", limit);
        List<EmbeddingWork> claimed = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            long chunkId = number(row.get("chunk_id"));
            int updated = jdbcTemplate.update("UPDATE agent_knowledge_chunk_embedding SET status='PROCESSING', "
                    + "attempt_count=attempt_count+1, updated_at=CURRENT_TIMESTAMP "
                    + "WHERE chunk_id=? AND status='PENDING' AND EXISTS ("
                    + "SELECT 1 FROM agent_knowledge_chunk c "
                    + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                    + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                    + "WHERE c.chunk_id=agent_knowledge_chunk_embedding.chunk_id "
                    + "AND d.extraction_status='READY' AND s.extraction_status='READY' "
                    + "AND s.invalidated_at IS NULL)", chunkId);
            if (updated == 1) claimed.add(new EmbeddingWork(chunkId,
                    String.valueOf(row.getOrDefault("content_hash", "")),
                    String.valueOf(row.getOrDefault("content", ""))));
        }
        return claimed;
    }

    private List<EmbeddingWork> revalidateWork(List<EmbeddingWork> work) {
        if (work.isEmpty()) return work;
        String placeholders = String.join(",", Collections.nCopies(work.size(), "?"));
        List<Object> args = new ArrayList<>();
        for (EmbeddingWork item : work) args.add(item.chunkId);
        List<Long> validIds = jdbcTemplate.query(
                "SELECT c.chunk_id FROM agent_knowledge_chunk c "
                        + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                        + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                        + "JOIN agent_knowledge_chunk_embedding e ON e.chunk_id=c.chunk_id "
                        + "WHERE c.chunk_id IN (" + placeholders + ") AND e.status='PROCESSING' "
                        + "AND d.extraction_status='READY' AND s.extraction_status='READY' "
                        + "AND s.invalidated_at IS NULL", (rs, rowNum) -> rs.getLong(1), args.toArray());
        List<EmbeddingWork> valid = new ArrayList<>();
        for (EmbeddingWork item : work) if (validIds.contains(item.chunkId)) valid.add(item);
        return valid;
    }

    /**
     * Worker 在 HTTP 调用期间被重启时，已领取的任务不会再有线程写回状态。超时后
     * 将其回收到待处理队列；保留 attempt_count，避免持续崩溃的任务无限重试。
     */
    int recoverTimedOutProcessing() {
        long timeout = Math.max(1_000L, processingTimeoutMillis);
        return jdbcTemplate.update("UPDATE agent_knowledge_chunk_embedding SET status='PENDING', "
                        + "last_error_code='EMBEDDING_WORKER_RECOVERED', next_retry_at=CURRENT_TIMESTAMP, "
                        + "updated_at=CURRENT_TIMESTAMP WHERE status='PROCESSING' "
                        + "AND updated_at < CURRENT_TIMESTAMP - (? * INTERVAL '1 millisecond')",
                timeout);
    }

    private void updateReady(long chunkId, String contentHash, List<Double> vector) {
        jdbcTemplate.update("UPDATE agent_knowledge_chunk_embedding SET content_hash=?, embedding_model=?, "
                        + "embedding_projected=CAST(? AS vector), status='READY', last_error_code=NULL, "
                        + "next_retry_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE chunk_id=? "
                        + "AND status='PROCESSING' AND content_hash=? AND EXISTS ("
                        + "SELECT 1 FROM agent_knowledge_chunk c "
                        + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                        + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                        + "WHERE c.chunk_id=agent_knowledge_chunk_embedding.chunk_id "
                        + "AND c.content_hash=? AND d.extraction_status='READY' "
                        + "AND s.extraction_status='READY' AND s.invalidated_at IS NULL)",
                contentHash, modelKey(), vectorLiteral(vector), chunkId, contentHash, contentHash);
    }

    private void updateFailure(long chunkId, String errorCode) {
        jdbcTemplate.update("UPDATE agent_knowledge_chunk_embedding SET status=CASE WHEN attempt_count>=? "
                        + "THEN 'FAILED' ELSE 'PENDING' END, last_error_code=?, "
                        + "next_retry_at=CURRENT_TIMESTAMP + (LEAST(attempt_count, 10) * INTERVAL '1 minute'), "
                        + "updated_at=CURRENT_TIMESTAMP WHERE chunk_id=? AND EXISTS ("
                        + "SELECT 1 FROM agent_knowledge_chunk c "
                        + "JOIN agent_knowledge_document d ON d.document_id=c.document_id "
                        + "JOIN agent_knowledge_source s ON s.source_id=d.source_id "
                        + "WHERE c.chunk_id=agent_knowledge_chunk_embedding.chunk_id "
                        + "AND d.extraction_status='READY' AND s.extraction_status='READY' "
                        + "AND s.invalidated_at IS NULL)",
                MAX_RETRIES, errorCode, chunkId);
    }

    @SuppressWarnings("unchecked")
    private List<Double> queryEmbedding(String input) {
        return queryEmbeddings(Collections.singletonList(input)).get(0);
    }

    @SuppressWarnings("unchecked")
    private List<List<Double>> queryEmbeddings(List<String> inputs) {
        if (inputs == null || inputs.isEmpty()) throw new IllegalArgumentException("EMBEDDING_INPUT_EMPTY");
        for (String input : inputs) {
            if (!StringUtils.hasText(input)) throw new IllegalArgumentException("EMBEDDING_INPUT_EMPTY");
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(embeddingApiKey);
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("model", embeddingModel);
        request.put("input", inputs);
        try {
            ResponseEntity<Map> response = embeddingRestTemplate().exchange(endpoint(), HttpMethod.POST,
                    new HttpEntity<>(request, headers), Map.class);
            Object rawData = response.getBody() == null ? null : response.getBody().get("data");
            int expected = sourceDimensions > 0 ? sourceDimensions : DEFAULT_SOURCE_DIMENSIONS;
            return decodeEmbeddingVectors(rawData instanceof List ? (List<?>) rawData : Collections.emptyList(),
                    inputs.size(), expected);
        } catch (RuntimeException ex) {
            throw ex;
        }
    }

    /** 将 OpenAI 兼容响应按 data[index] 放回请求顺序，绝不信任返回列表的自然顺序。 */
    static List<List<Double>> decodeEmbeddingVectors(List<?> data, int inputCount, int expectedDimensions) {
        if (data == null || data.size() != inputCount || inputCount <= 0 || expectedDimensions <= 0) {
            throw new IllegalStateException("EMBEDDING_RESPONSE_INVALID");
        }
        List<List<Double>> vectors = new ArrayList<>(Collections.nCopies(inputCount, null));
        for (Object item : data) {
            if (!(item instanceof Map)) throw new IllegalStateException("EMBEDDING_RESPONSE_INVALID");
            Map<?, ?> row = (Map<?, ?>) item;
            Object rawIndex = row.get("index");
            if (!(rawIndex instanceof Number)) throw new IllegalStateException("EMBEDDING_RESPONSE_INVALID");
            Number number = (Number) rawIndex;
            int index = number.intValue();
            if (number.doubleValue() != index || index < 0 || index >= inputCount || vectors.get(index) != null) {
                throw new IllegalStateException("EMBEDDING_RESPONSE_INVALID");
            }
            Object rawVector = row.get("embedding");
            if (!(rawVector instanceof List)) throw new IllegalStateException("EMBEDDING_VECTOR_MISSING");
            List<?> values = (List<?>) rawVector;
            if (values.size() != expectedDimensions) throw new IllegalStateException("EMBEDDING_DIMENSION_MISMATCH");
            List<Double> full = new ArrayList<>();
            for (Object value : values) {
                if (!(value instanceof Number) || !Double.isFinite(((Number) value).doubleValue())) {
                    throw new IllegalStateException("EMBEDDING_VECTOR_INVALID");
                }
                full.add(((Number) value).doubleValue());
            }
            vectors.set(index, project(full));
        }
        for (List<Double> vector : vectors) {
            if (vector == null) throw new IllegalStateException("EMBEDDING_RESPONSE_INVALID");
        }
        return vectors;
    }

    /** 与既有 Qwen/党务向量一致的稳定特征投影，输入输出双方必须使用同一版本。 */
    static List<Double> project(List<Double> full) {
        double[] projected = new double[PROJECTED_DIMENSIONS];
        for (int index = 0; index < full.size(); index++) {
            byte[] digest = digest("party-projection:" + index);
            long unsignedBucket = ((long) (digest[0] & 0xFF) << 24) | ((long) (digest[1] & 0xFF) << 16)
                    | ((long) (digest[2] & 0xFF) << 8) | (digest[3] & 0xFFL);
            int bucket = (int) (unsignedBucket % PROJECTED_DIMENSIONS);
            projected[bucket] += (digest[4] & 1) == 1 ? full.get(index) : -full.get(index);
        }
        double norm = 0D;
        for (double value : projected) norm += value * value;
        norm = Math.sqrt(norm);
        if (norm == 0D) throw new IllegalStateException("EMBEDDING_VECTOR_ZERO");
        List<Double> result = new ArrayList<>();
        for (double value : projected) result.add(value / norm);
        return result;
    }

    private String endpoint() {
        return embeddingBaseUrl.replaceAll("/+$", "") + "/embeddings";
    }

    private RestTemplate embeddingRestTemplate() {
        int timeout = (int) Math.min(Integer.MAX_VALUE, Math.max(1000L, timeoutMillis));
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        return new RestTemplate(factory);
    }

    private String modelKey() {
        return embeddingModel + "@" + (sourceDimensions > 0 ? sourceDimensions : DEFAULT_SOURCE_DIMENSIONS)
                + ":projection-v1";
    }

    private static String vectorLiteral(List<Double> vector) {
        StringBuilder value = new StringBuilder("[");
        for (int index = 0; index < vector.size(); index++) {
            if (index > 0) value.append(',');
            value.append(String.format(Locale.ROOT, "%.9f", vector.get(index)));
        }
        return value.append(']').toString();
    }

    private static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.US_ASCII));
        } catch (Exception ex) {
            throw new IllegalStateException("EMBEDDING_PROJECTION_FAILED", ex);
        }
    }

    private static long number(Object value) {
        return value instanceof Number ? ((Number) value).longValue() : Long.parseLong(String.valueOf(value));
    }

    private static String safeError(RuntimeException ex) {
        String message = ex.getMessage();
        if (message != null && message.matches("[A-Z][A-Z0-9_]{2,127}")) return message;
        String simpleName = ex.getClass().getSimpleName().replaceAll("[^A-Za-z0-9_]", "_");
        return StringUtils.hasText(simpleName) ? simpleName : "EMBEDDING_FAILED";
    }

    static final class SemanticSearch {
        final boolean available;
        final List<Map<String, Object>> candidates;
        final String failureCode;

        private SemanticSearch(boolean available, List<Map<String, Object>> candidates, String failureCode) {
            this.available = available;
            this.candidates = candidates;
            this.failureCode = failureCode;
        }

        static SemanticSearch available(List<Map<String, Object>> candidates) {
            return new SemanticSearch(true, candidates, null);
        }

        static SemanticSearch unavailable(String failureCode) {
            return new SemanticSearch(false, Collections.emptyList(), failureCode);
        }
    }

    /** 只用于服务端灰度与离线评测；请求 API 和模型工具均不能覆盖此设置。 */
    enum RetrievalMode {
        KEYWORD,
        SEMANTIC,
        HYBRID
    }

    private static final class EmbeddingWork {
        final long chunkId;
        final String contentHash;
        final String content;

        private EmbeddingWork(long chunkId, String contentHash, String content) {
            this.chunkId = chunkId;
            this.contentHash = contentHash;
            this.content = content;
        }
    }
}
