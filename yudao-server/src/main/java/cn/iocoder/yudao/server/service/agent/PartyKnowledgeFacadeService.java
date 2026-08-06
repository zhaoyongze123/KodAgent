package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.pojo.PageParam;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.Citation;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.ChunkResponse;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.DocumentResponse;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.SearchHit;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.SearchRequest;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.SearchResponse;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Authorization boundary for derived party-file knowledge.
 *
 * <p>PostgreSQL tenant columns narrow the candidate set only. The final fact
 * is PartyFileService's employee visibility rule, evaluated with the current
 * SecurityContext user before any derived document or chunk is returned.</p>
 */
@Service
public class PartyKnowledgeFacadeService {

    private static final String READY = "READY";

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Resource
    private PartyFileService partyFileService;

    /** Read-only operational evidence for validating the real PG/vector path. */
    public Map<String, Object> health(Long tenantId, Long userId) {
        requireIdentity(tenantId, userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("tenantId", tenantId);
        result.put("vectorExtension", exists("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"));
        result.put("projectedColumn", exists("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_chunk' AND column_name = 'embedding_projected')"));
        result.put("readyDocuments", count("SELECT COUNT(*) FROM knowledge_document WHERE tenant_id = ? AND status = ?", tenantId, READY));
        result.put("readyChunks", count("SELECT COUNT(*) FROM knowledge_chunk c JOIN knowledge_document d ON d.id = c.document_id WHERE d.tenant_id = ? AND d.status = ? AND c.status = ?", tenantId, READY, READY));
        result.put("embeddedChunks", count("SELECT COUNT(*) FROM knowledge_chunk c JOIN knowledge_document d ON d.id = c.document_id WHERE d.tenant_id = ? AND d.status = ? AND c.status = ? AND c.embedding_projected IS NOT NULL", tenantId, READY, READY));
        result.put("retrievalReady", Boolean.TRUE.equals(result.get("readyChunks")) || ((Number) result.get("readyChunks")).longValue() > 0);
        result.put("checkedAt", java.time.OffsetDateTime.now());
        return result;
    }

    public SearchResponse search(Long tenantId, Long userId, String userNickname, SearchRequest request) {
        requireIdentity(tenantId, userId);
        String query = request.getQuery().trim();
        if (query.length() > 200) {
            throw ServiceExceptionUtil.exception0(400, "知识检索关键词最长 200 个字符");
        }
        Set<Long> visiblePartyFileIds = visiblePartyFileIds(userId);
        SearchResponse response = new SearchResponse();
        response.setQuery(query);
        if (visiblePartyFileIds.isEmpty()) {
            response.setHits(Collections.emptyList());
            response.setTotal(0);
            response.setRetrievalMode("no_visible_documents");
            return response;
        }

        RetrievalResult retrieval = queryChunks(tenantId, visiblePartyFileIds, query,
                nullable(request.getDocumentType()), request.getTopK(), request.getEmbedding(), request.getEmbeddingProjected());
        List<SearchHit> hits = new ArrayList<>();
        Set<Long> recheckedSources = new LinkedHashSet<>();
        for (ChunkRecord candidate : retrieval.chunks) {
            // A visibility page is only a snapshot. Re-check through the OA
            // service immediately before exposing each source's derived text.
            if (recheckedSources.add(candidate.sourcePartyFileId)) {
                requireSourceVisible(candidate.sourcePartyFileId, userId, userNickname, visiblePartyFileIds);
            }
            hits.add(toSearchHit(candidate));
        }
        response.setHits(hits);
        response.setTotal(hits.size());
        response.setRetrievalMode(retrieval.mode);
        return response;
    }

    public DocumentResponse getDocument(Long tenantId, Long userId, String userNickname, Long documentId) {
        requireIdentity(tenantId, userId);
        DocumentRecord document = findDocument(tenantId, documentId);
        requireSourceVisible(document.sourcePartyFileId, userId, userNickname, visiblePartyFileIds(userId));
        return toDocumentResponse(document);
    }

    public ChunkResponse getChunk(Long tenantId, Long userId, String userNickname, Long chunkId) {
        requireIdentity(tenantId, userId);
        ChunkRecord chunk = findChunk(tenantId, chunkId);
        requireSourceVisible(chunk.sourcePartyFileId, userId, userNickname, visiblePartyFileIds(userId));
        return toChunkResponse(chunk);
    }

    private Set<Long> visiblePartyFileIds(Long userId) {
        PartyFileMyPageReqVO request = new PartyFileMyPageReqVO();
        request.setPageNo(1);
        // This is an internal service invocation. PAGE_SIZE_NONE deliberately
        // evaluates the complete employee-visible fact set before PG lookup.
        request.setPageSize(PageParam.PAGE_SIZE_NONE);
        PageResult<PartyFileRespVO> page = partyFileService.getMyPartyFilePage(userId, request);
        if (page == null || page.getList() == null) return Collections.emptySet();
        return page.getList().stream().map(PartyFileRespVO::getId)
                .filter(id -> id != null).collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private RetrievalResult queryChunks(Long tenantId, Set<Long> visiblePartyFileIds, String query,
                                        String documentType, Integer topK, List<BigDecimal> embedding,
                                        List<BigDecimal> embeddingProjected) {
        boolean useProjected = embeddingProjected != null && embeddingProjected.size() == 1536 && projectedVectorAvailable();
        boolean useVector = !useProjected && embedding != null && embedding.size() == 4096 && vectorAvailable();
        String vectorLiteral = useProjected
                ? embeddingProjected.stream().map(String::valueOf).collect(Collectors.joining(",", "[", "]"))
                : (useVector ? embedding.stream().map(String::valueOf).collect(Collectors.joining(",", "[", "]")) : null);
        int resultLimit = Math.max(1, Math.min(topK == null ? 5 : topK, 20));
        QueryScope scope = queryScope(tenantId, visiblePartyFileIds, documentType);
        List<ChunkRecord> keywordCandidates = queryKeywordCandidates(scope, query, candidateLimit(resultLimit));
        if (!(useProjected || useVector)) {
            return new RetrievalResult(keywordCandidates.subList(0, Math.min(resultLimit, keywordCandidates.size())), "keyword");
        }
        try {
            List<ChunkRecord> vectorCandidates = queryVectorCandidates(
                    scope, vectorLiteral, useProjected ? "embedding_projected" : "embedding", candidateLimit(resultLimit));
            if (vectorCandidates.isEmpty()) {
                return new RetrievalResult(keywordCandidates.subList(0, Math.min(resultLimit, keywordCandidates.size())), "keyword_degraded_no_vectors");
            }
            return new RetrievalResult(rerankHybrid(vectorCandidates, keywordCandidates, resultLimit), "hybrid");
        } catch (RuntimeException ignored) {
            // pgvector must improve recall, not make an authorized keyword
            // query unavailable. The response carries this degraded state so
            // callers and telemetry can distinguish it from normal hybrid use.
            return new RetrievalResult(keywordCandidates.subList(0, Math.min(resultLimit, keywordCandidates.size())), "keyword_degraded_vector_unavailable");
        }
    }

    private QueryScope queryScope(Long tenantId, Set<Long> visiblePartyFileIds, String documentType) {
        String placeholders = visiblePartyFileIds.stream().map(id -> "?").collect(Collectors.joining(","));
        StringBuilder where = new StringBuilder("d.tenant_id = ? AND d.status = ? AND c.status = ? "
                + "AND d.source_party_file_id IN (").append(placeholders).append(") ");
        List<Object> args = new ArrayList<>();
        args.add(tenantId);
        args.add(READY);
        args.add(READY);
        args.addAll(visiblePartyFileIds);
        if (documentType != null) {
            where.append("AND d.document_type = ? ");
            args.add(documentType);
        }
        return new QueryScope(where.toString(), args);
    }

    private List<ChunkRecord> queryVectorCandidates(QueryScope scope, String vectorLiteral, String vectorColumn, int limit) {
        String sql = "SELECT c.id chunk_id, d.id document_id, d.source_party_file_id, d.title, d.document_type, "
                + "c.section, c.ordinal, c.content, (1 - (c." + vectorColumn + " <=> ?::vector)) score "
                + "FROM knowledge_chunk c JOIN knowledge_document d ON d.id = c.document_id WHERE " + scope.where
                + "AND c." + vectorColumn + " IS NOT NULL ORDER BY c." + vectorColumn + " <=> ?::vector ASC, c.id ASC LIMIT ?";
        List<Object> args = new ArrayList<>();
        args.add(vectorLiteral);
        args.addAll(scope.args);
        args.add(vectorLiteral);
        args.add(limit);
        return queryRecords(sql, args);
    }

    private List<ChunkRecord> queryKeywordCandidates(QueryScope scope, String query, int limit) {
        String pattern = "%" + query + "%";
        String sql = "SELECT c.id chunk_id, d.id document_id, d.source_party_file_id, d.title, d.document_type, "
                + "c.section, c.ordinal, c.content, "
                + "(ts_rank_cd(COALESCE(c.search_vector, ''::tsvector), websearch_to_tsquery('simple', ?)) "
                + "+ CASE WHEN lower(c.content) LIKE lower(?) OR lower(d.title) LIKE lower(?) THEN 1.0 ELSE 0.0 END) score "
                + "FROM knowledge_chunk c JOIN knowledge_document d ON d.id = c.document_id WHERE " + scope.where
                + "AND (COALESCE(c.search_vector, ''::tsvector) @@ websearch_to_tsquery('simple', ?) "
                + "OR lower(c.content) LIKE lower(?) OR lower(d.title) LIKE lower(?)) "
                + "ORDER BY score DESC, c.ordinal ASC, c.id ASC LIMIT ?";
        List<Object> args = new ArrayList<>();
        args.add(query);
        args.add(pattern);
        args.add(pattern);
        args.addAll(scope.args);
        args.add(query);
        args.add(pattern);
        args.add(pattern);
        args.add(limit);
        return queryRecords(sql, args);
    }

    private List<ChunkRecord> queryRecords(String sql, List<Object> args) {
        return jdbcTemplate.query(sql, (rs, rowNum) -> new ChunkRecord(
                rs.getLong("chunk_id"), rs.getLong("document_id"), rs.getLong("source_party_file_id"),
                rs.getString("title"), rs.getString("document_type"), rs.getString("section"),
                rs.getInt("ordinal"), rs.getString("content"), rs.getBigDecimal("score")), args.toArray());
    }

    private List<ChunkRecord> rerankHybrid(List<ChunkRecord> vectorCandidates, List<ChunkRecord> keywordCandidates, int limit) {
        Map<Long, HybridCandidate> merged = new LinkedHashMap<>();
        for (ChunkRecord record : vectorCandidates) {
            merged.computeIfAbsent(record.chunkId, ignored -> new HybridCandidate(record)).semanticScore = record.score.doubleValue();
        }
        for (ChunkRecord record : keywordCandidates) {
            merged.computeIfAbsent(record.chunkId, ignored -> new HybridCandidate(record)).keywordScore = record.score.doubleValue();
        }
        return merged.values().stream()
                .map(candidate -> candidate.withHybridScore())
                .sorted(Comparator.comparing((ChunkRecord item) -> item.score).reversed()
                        .thenComparing(item -> item.ordinal).thenComparing(item -> item.chunkId))
                .limit(limit)
                .collect(Collectors.toList());
    }

    private int candidateLimit(int resultLimit) {
        return Math.min(100, Math.max(10, resultLimit * 5));
    }

    private boolean vectorAvailable() {
        try {
            return Boolean.TRUE.equals(jdbcTemplate.queryForObject("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')", Boolean.class));
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private boolean projectedVectorAvailable() {
        try {
            return Boolean.TRUE.equals(jdbcTemplate.queryForObject(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                            + "WHERE table_name = 'knowledge_chunk' AND column_name = 'embedding_projected')",
                    Boolean.class));
        } catch (RuntimeException ignored) {
            return false;
        }
    }

    private boolean exists(String sql) {
        try { return Boolean.TRUE.equals(jdbcTemplate.queryForObject(sql, Boolean.class)); }
        catch (RuntimeException ignored) { return false; }
    }

    private long count(String sql, Object... args) {
        try { Number value = jdbcTemplate.queryForObject(sql, Number.class, args); return value == null ? 0L : value.longValue(); }
        catch (RuntimeException ignored) { return 0L; }
    }

    private DocumentRecord findDocument(Long tenantId, Long documentId) {
        List<DocumentRecord> rows = jdbcTemplate.query("SELECT id, source_party_file_id, title, document_type "
                        + "FROM knowledge_document WHERE id = ? AND tenant_id = ? AND status = ?",
                (rs, rowNum) -> new DocumentRecord(rs.getLong("id"), rs.getLong("source_party_file_id"),
                        rs.getString("title"), rs.getString("document_type")), documentId, tenantId, READY);
        if (rows.isEmpty()) throw notFound();
        return rows.get(0);
    }

    private ChunkRecord findChunk(Long tenantId, Long chunkId) {
        List<ChunkRecord> rows = jdbcTemplate.query("SELECT c.id chunk_id, d.id document_id, d.source_party_file_id, "
                        + "d.title, d.document_type, c.section, c.ordinal, c.content, 1.0 score "
                        + "FROM knowledge_chunk c JOIN knowledge_document d ON d.id = c.document_id "
                        + "WHERE c.id = ? AND d.tenant_id = ? AND d.status = ? AND c.status = ?",
                (rs, rowNum) -> new ChunkRecord(rs.getLong("chunk_id"), rs.getLong("document_id"),
                        rs.getLong("source_party_file_id"), rs.getString("title"), rs.getString("document_type"),
                        rs.getString("section"), rs.getInt("ordinal"), rs.getString("content"), rs.getBigDecimal("score")),
                chunkId, tenantId, READY, READY);
        if (rows.isEmpty()) throw notFound();
        return rows.get(0);
    }

    private void requireSourceVisible(Long sourcePartyFileId, Long userId, String userNickname,
                                      Set<Long> visiblePartyFileIds) {
        if (!visiblePartyFileIds.contains(sourcePartyFileId)) throw notFound();
        // This service applies the definitive ALL/USER/DEPT/ROLE rule again,
        // protects against a page-to-read TOCTOU change, and records reading
        // only after the user actually consumes knowledge from that document.
        partyFileService.getMyPartyFileDetail(sourcePartyFileId, userId, userNickname);
    }

    private void requireIdentity(Long tenantId, Long userId) {
        if (tenantId == null || userId == null) {
            throw ServiceExceptionUtil.exception0(401, "缺少当前用户或租户身份");
        }
    }

    private RuntimeException notFound() {
        // Deliberately use one response for absent and inaccessible records.
        return ServiceExceptionUtil.exception0(404, "知识文档不存在或当前用户无权访问");
    }

    private String nullable(String value) {
        return value == null || value.trim().isEmpty() ? null : value.trim();
    }

    private DocumentResponse toDocumentResponse(DocumentRecord record) {
        DocumentResponse response = new DocumentResponse();
        response.setId(record.id);
        response.setTitle(record.title);
        response.setType(record.type);
        return response;
    }

    private ChunkResponse toChunkResponse(ChunkRecord record) {
        ChunkResponse response = new ChunkResponse();
        response.setId(record.chunkId);
        response.setDocumentId(record.documentId);
        response.setTitle(record.title);
        response.setType(record.type);
        response.setSection(record.section);
        response.setOrdinal(record.ordinal);
        response.setContent(record.content);
        response.setCitation(citation(record));
        return response;
    }

    private SearchHit toSearchHit(ChunkRecord record) {
        SearchHit response = new SearchHit();
        response.setId(record.chunkId);
        response.setTitle(record.title);
        response.setType(record.type);
        response.setSection(record.section);
        response.setOrdinal(record.ordinal);
        response.setScore(record.score == null ? BigDecimal.ZERO : record.score);
        response.setContent(record.content);
        response.setCitation(citation(record));
        return response;
    }

    private Citation citation(ChunkRecord record) {
        Citation citation = new Citation();
        citation.setDocumentId(record.documentId);
        citation.setChunkId(record.chunkId);
        citation.setSection(record.section);
        citation.setOrdinal(record.ordinal);
        return citation;
    }

    private static final class DocumentRecord {
        private final Long id;
        private final Long sourcePartyFileId;
        private final String title;
        private final String type;

        private DocumentRecord(Long id, Long sourcePartyFileId, String title, String type) {
            this.id = id; this.sourcePartyFileId = sourcePartyFileId; this.title = title; this.type = type;
        }
    }

    private static final class ChunkRecord {
        private final Long chunkId;
        private final Long documentId;
        private final Long sourcePartyFileId;
        private final String title;
        private final String type;
        private final String section;
        private final Integer ordinal;
        private final String content;
        private final BigDecimal score;

        private ChunkRecord(Long chunkId, Long documentId, Long sourcePartyFileId, String title, String type,
                            String section, Integer ordinal, String content, BigDecimal score) {
            this.chunkId = chunkId; this.documentId = documentId; this.sourcePartyFileId = sourcePartyFileId;
            this.title = title; this.type = type; this.section = section; this.ordinal = ordinal;
            this.content = content; this.score = score;
        }
    }

    private static final class QueryScope {
        private final String where;
        private final List<Object> args;

        private QueryScope(String where, List<Object> args) {
            this.where = where;
            this.args = args;
        }
    }

    private static final class RetrievalResult {
        private final List<ChunkRecord> chunks;
        private final String mode;

        private RetrievalResult(List<ChunkRecord> chunks, String mode) {
            this.chunks = chunks;
            this.mode = mode;
        }
    }

    private static final class HybridCandidate {
        private final ChunkRecord record;
        private double semanticScore;
        private double keywordScore;

        private HybridCandidate(ChunkRecord record) {
            this.record = record;
        }

        private ChunkRecord withHybridScore() {
            // Cosine similarity falls in [-1, 1]; ts_rank is unbounded, so
            // normalize both independently before applying the documented
            // 85/15 semantic/lexical blend.
            double semantic = Math.max(0.0d, Math.min(1.0d, (semanticScore + 1.0d) / 2.0d));
            double keyword = Math.max(0.0d, Math.min(1.0d, keywordScore));
            return new ChunkRecord(record.chunkId, record.documentId, record.sourcePartyFileId,
                    record.title, record.type, record.section, record.ordinal, record.content,
                    BigDecimal.valueOf(0.85d * semantic + 0.15d * keyword));
        }
    }
}
