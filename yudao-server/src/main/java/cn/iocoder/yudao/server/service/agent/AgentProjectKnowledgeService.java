package cn.iocoder.yudao.server.service.agent;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserNickname;

/**
 * 项目资料的全文检索副本。
 *
 * <p>本类不把索引当事实源：每次同步先从 KodCloud project bridge 获取当前用户可见
 * 的文件元数据，读取正文前再次走文件权限校验；返回命中前也会复核文件是否仍在目录中。
 * PostgreSQL 只保存派生文本、哈希和版本，删除或失权的文件会立即标记为失效。</p>
 *
 * <p>TXT/Markdown、DOCX/XLSX 和可提取文字的 PDF 会建立全文索引；可选的向量副本只
 * 用于扩展召回。扫描件、图片和无法提取的 PDF 明确标记 NEEDS_OCR，绝不伪造“已读”。</p>
 */
@Service
public class AgentProjectKnowledgeService {

    private static final String READY = "READY";
    private static final int CHUNK_SIZE = 1800;
    private static final int MAX_FALLBACK_TERMS = 48;
    private static final int RETRIEVAL_CANDIDATE_LIMIT = 30;
    private static final int RRF_K = 60;
    private static final Pattern CJK_RUN = Pattern.compile("[\\p{IsHan}]{2,}");
    private static final Pattern LATIN_TERM = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{1,}");
    /**
     * 这些词在中文自然问句中只承担语气或指代作用，不能单独作为检索证据。
     * 这里不试图实现中文分词器，而是避免它们把“为什么还没闭合”降级成泛匹配。
     */
    private static final Set<String> QUERY_FILLERS = new LinkedHashSet<>(Arrays.asList(
            "请问", "帮我", "我们", "你们", "这个", "那个", "什么", "怎么", "为何", "为什么",
            "哪些", "一下", "目前", "当前", "还有", "是否", "能否", "可以", "需要", "相关",
            "关于", "情况", "问题", "要求", "项目", "资料", "没有", "已经", "正在", "进行"));

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Resource
    private KodProjectBridgeService bridgeService;
    @Resource
    private AgentProjectAuditService auditService;
    @Resource
    private AgentProjectEmbeddingService embeddingService;
    @Resource
    private AgentKnowledgeLibraryService libraryService;

    /**
     * 检索项目资料和管理员维护的制度库。
     * 参数 projectId：项目编号；query：用户问题；topK：最多返回的证据条数；
     * includePolicyLibrary：是否同时包含当前租户中管理员已启用的制度来源。
     */
    public Map<String, Object> search(Long tenantId, Long userId, long projectId,
                                      String query, int topK, boolean includePolicyLibrary) {
        if (tenantId == null || userId == null || projectId <= 0) {
            throw new IllegalArgumentException("项目知识检索缺少当前用户或项目编号");
        }
        if (!StringUtils.hasText(query) || query.trim().length() > 200) {
            throw new IllegalArgumentException("项目知识检索关键词不能为空且最多 200 个字符");
        }
        long startedAtNanos = System.nanoTime();
        // 索引写入只能由定时/手动同步触发。检索路径只复核实时权限与文件版本，
        // 否则每个用户问题都会重新读取并重建整个项目资料目录，既制造审计噪声，
        // 也会让并行 Agent 查询把一次同步放大成多次。
        Map<String, Object> visibleDocuments = bridgeService.documents(tenantId, userId, projectId);
        Set<Long> visibleFileIds = new LinkedHashSet<>();
        Map<Long, String> visibleVersions = new LinkedHashMap<>();
        for (Map<String, Object> item : maps(visibleDocuments.get("items"))) {
            Object id = item.get("fileID");
            if (id == null) continue;
            long fileId = number(id);
            if (fileId <= 0) continue;
            visibleFileIds.add(fileId);
            visibleVersions.put(fileId, String.valueOf(item.getOrDefault("version",
                    item.getOrDefault("contentHash", ""))));
        }

        boolean policyEnabled = includePolicyLibrary && bridgeService.hasPolicyLibrary(tenantId);
        // 目录资料的索引由管理员维护，但检索必须按当前提问用户的 KodCloud 身份
        // 重新列举可见文件；库配置里的 owner_user_id 绝不能替代用户授权事实。
        Map<Long, Map<Long, String>> folderVisibleVersions = new LinkedHashMap<>();
        if (includePolicyLibrary) {
            for (Map<String, Object> library : libraryService.activeKodFolders()) {
                if (!tenantId.equals(numberObject(library.get("tenantId")))) continue;
                long libraryId = number(library.get("libraryId"));
                long folderId = number(library.get("folderId"));
                if (libraryId <= 0 || folderId <= 0) continue;
                try {
                    Map<String, Object> visible = bridgeService.knowledgeDocuments(tenantId, userId, folderId);
                    Map<Long, String> versions = new LinkedHashMap<>();
                    for (Map<String, Object> item : maps(visible.get("items"))) {
                        long fileId = number(item.get("fileID"));
                        if (fileId > 0) versions.put(fileId, String.valueOf(item.getOrDefault("version",
                                item.getOrDefault("contentHash", ""))));
                    }
                    folderVisibleVersions.put(libraryId, versions);
                } catch (RuntimeException ignored) {
                    // 当前用户无映射、失权或目录暂不可用时不把该目录索引视为可读；
                    // 不吞掉项目资料本身的检索结果，也不退化为管理员身份。
                }
            }
        }
        List<Long> visibleLocalLibraryIds = includePolicyLibrary
                ? libraryService.visibleLocalLibraryIds(tenantId, userId) : Collections.<Long>emptyList();
        StringBuilder sourceSql = new StringBuilder(
                "SELECT source_id, source_type, project_id, kod_file_id, library_id, display_name, document_type, content_version "
                        + "FROM agent_knowledge_source WHERE tenant_id = ? AND extraction_status = ? "
                        + "AND invalidated_at IS NULL "
                        + "AND ((source_type = 'PROJECT_FILES' AND project_id = ? AND kod_file_id IN (");
        List<Object> args = new ArrayList<>();
        args.add(tenantId);
        args.add(READY);
        args.add(projectId);
        if (visibleFileIds.isEmpty()) {
            sourceSql.append("NULL");
        } else {
            sourceSql.append(String.join(",", Collections.nCopies(visibleFileIds.size(), "?")));
            args.addAll(visibleFileIds);
        }
        // 这里的外层括号同时约束“项目资料”和可选的“制度库”。无论制度库是否启用，
        // 都必须闭合两层括号，避免 PostgreSQL 在 ORDER BY 前遇到未结束的条件表达式。
        // 首个右括号关闭 IN；第二个右括号关闭 PROJECT_FILES 条件组。
        sourceSql.append("))");
        if (policyEnabled) {
            sourceSql.append(" OR source_type = 'POLICY_LIBRARY'");
        }
        for (Map.Entry<Long, Map<Long, String>> entry : folderVisibleVersions.entrySet()) {
            if (entry.getValue().isEmpty()) continue;
            sourceSql.append(" OR (source_type='KOD_FOLDER' AND library_id=? AND kod_file_id IN (");
            sourceSql.append(String.join(",", Collections.nCopies(entry.getValue().size(), "?"))).append("))");
            args.add(entry.getKey()); args.addAll(entry.getValue().keySet());
        }
        if (!visibleLocalLibraryIds.isEmpty()) {
            sourceSql.append(" OR (source_type='LOCAL_UPLOAD' AND library_id IN (");
            sourceSql.append(String.join(",", Collections.nCopies(visibleLocalLibraryIds.size(), "?"))).append("))");
            args.addAll(visibleLocalLibraryIds);
        }
        // 最后一个右括号关闭整个“项目资料或制度库”的来源范围。
        sourceSql.append(") ORDER BY source_id");
        List<Map<String, Object>> sources = jdbcTemplate.query(sourceSql.toString(), (rs, rowNum) -> {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sourceId", rs.getLong("source_id"));
            item.put("sourceType", rs.getString("source_type"));
            item.put("projectId", rs.getObject("project_id"));
            item.put("fileId", rs.getObject("kod_file_id"));
            item.put("libraryId", rs.getObject("library_id"));
            item.put("name", rs.getString("display_name"));
            item.put("documentType", rs.getString("document_type"));
            item.put("contentVersion", rs.getString("content_version"));
            return item;
        }, args.toArray());
        // 文件被替换后，在下一次 15 分钟同步或管理员手动同步完成前，不能把旧正文
        // 当作最新资料返回。版本不一致的文件暂时不参与搜索；权限仍以本次 bridge
        // 返回的实时可见列表为准。
        sources = currentSources(sources, visibleVersions);
        sources = currentFolderSources(sources, folderVisibleVersions);
        if (sources.isEmpty()) {
            auditService.record(tenantId, userId, projectId, "SEARCH", epoch(visibleDocuments.get("asOf")),
                    Collections.<Map<String, Object>>emptyList(), null, null,
                    retrievalAuditMetadata("keyword", 0, 0, 0, 0, false, "NOT_REQUESTED",
                            elapsedMillis(startedAtNanos)));
            return result(query, "keyword", Collections.emptyList(), visibleDocuments.get("asOf"));
        }

        List<Object> sourceIds = new ArrayList<>();
        for (Map<String, Object> source : sources) sourceIds.add(source.get("sourceId"));
        String placeholders = String.join(",", Collections.nCopies(sourceIds.size(), "?"));
        int limit = Math.min(20, Math.max(1, topK));
        List<String> fallbackTerms = keywordTerms(query);
        // PostgreSQL simple 配置不负责中文分词。原实现把整句自然语言直接 ILIKE，
        // 例如“历史建筑保护范围为什么还没有闭合”不会出现在正文中，导致已经索引的
        // 资料被误判为没有命中。现在仍以 PostgreSQL 全文检索为主，但在已完成权限
        // 复核的 source_id 范围内，将中文连续片段拆为受限的 2 至 8 字词块，再用
        // 参数化 ILIKE 召回候选、在 Java 侧按最长命中和标题命中确定性排序。
        // 这不是向量检索，也不把检索副本提升为权限或业务事实源。
        StringBuilder predicate = new StringBuilder(
                "c.search_vector @@ websearch_to_tsquery('simple', ?)");
        for (int i = 0; i < fallbackTerms.size(); i++) {
            predicate.append(" OR c.content ILIKE ? ESCAPE '\\' OR s.display_name ILIKE ? ESCAPE '\\'");
        }
        String sql = "SELECT c.chunk_id, d.source_id, s.source_type, s.project_id, s.kod_file_id, s.library_id, "
                + "s.display_name, s.document_type, s.content_version, c.section, c.ordinal, c.content, "
                + "ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', ?)) score "
                + "FROM agent_knowledge_chunk c JOIN agent_knowledge_document d ON d.document_id = c.document_id "
                + "JOIN agent_knowledge_source s ON s.source_id = d.source_id "
                + "WHERE s.source_id IN (" + placeholders + ") "
                + "AND (" + predicate + ") "
                + "ORDER BY c.ordinal ASC, c.chunk_id ASC LIMIT ?";
        List<Object> queryArgs = new ArrayList<>();
        queryArgs.add(query.trim());
        queryArgs.addAll(sourceIds);
        queryArgs.add(query.trim());
        for (String term : fallbackTerms) {
            String pattern = likePattern(term);
            queryArgs.add(pattern);
            queryArgs.add(pattern);
        }
        // SQL 只负责权限范围内的候选召回；实际前 K 名必须在中文命中分可比较后再截断。
        queryArgs.add(Math.min(240, Math.max(80, limit * 12)));
        List<Map<String, Object>> candidates = jdbcTemplate.query(sql, (rs, rowNum) -> {
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
            item.put("score", rs.getBigDecimal("score"));
            return item;
        }, queryArgs.toArray());
        List<Map<String, Object>> lexical = rankCandidates(candidates, fallbackTerms, RETRIEVAL_CANDIDATE_LIMIT);
        AgentProjectEmbeddingService.RetrievalMode configuredMode = embeddingService.retrievalMode();
        AgentProjectEmbeddingService.SemanticSearch semantic = configuredMode
                == AgentProjectEmbeddingService.RetrievalMode.KEYWORD
                ? AgentProjectEmbeddingService.SemanticSearch.unavailable("KEYWORD_MODE")
                : embeddingService.semanticCandidates(sourceIds, query.trim(), RETRIEVAL_CANDIDATE_LIMIT);
        List<Map<String, Object>> hits;
        if (!semantic.available) {
            hits = lexical.subList(0, Math.min(limit, lexical.size()));
        } else if (configuredMode == AgentProjectEmbeddingService.RetrievalMode.SEMANTIC) {
            hits = new ArrayList<>(semantic.candidates.subList(0, Math.min(limit, semantic.candidates.size())));
        } else {
            hits = mergeHybridCandidates(lexical, semantic.candidates, limit);
        }
        // 即使命中了索引，也不把历史 source_id 当权限事实。逐个文件重新比对当前
        // project bridge 的文件列表，失权的命中在本次响应中直接丢弃。
        List<Map<String, Object>> checked = new ArrayList<>();
        for (Map<String, Object> hit : hits) {
            if ("PROJECT_FILES".equals(hit.get("sourceType"))
                    && !visibleFileIds.contains(number(hit.get("fileId")))) continue;
            if ("KOD_FOLDER".equals(hit.get("sourceType")) && !visibleFolderSource(hit,
                    folderVisibleVersions.get(number(hit.get("libraryId"))))) continue;
            checked.add(evidence(hit, checked.size() + 1));
        }
        String mode = retrievalMode(configuredMode, semantic, embeddingService.isRagRequested());
        Map<String, Object> retrievalAudit = retrievalAuditMetadata(mode, lexical.size(), semantic.candidates.size(),
                checked.size(), Math.max(0, hits.size() - checked.size()), semantic.available, semantic.failureCode,
                elapsedMillis(startedAtNanos));
        String failureCode = semantic.available || !embeddingService.isRagRequested()
                || configuredMode == AgentProjectEmbeddingService.RetrievalMode.KEYWORD
                ? null : semantic.failureCode;
        auditService.record(tenantId, userId, projectId, "SEARCH", epoch(visibleDocuments.get("asOf")),
                sourceVersions(sources), null, failureCode, retrievalAudit);
        return result(query, mode, checked, visibleDocuments.get("asOf"));
    }

    /** 返回资料同步状态，供项目快照和管理员手动同步入口使用。 */
    public Map<String, Object> syncProject(Long tenantId, Long userId, long projectId, String mode) {
        long syncId = 0;
        try {
            Number created = jdbcTemplate.queryForObject(
                    "INSERT INTO agent_project_document_sync (tenant_id, project_id, requested_by_user_id, mode, status, started_at) "
                            + "VALUES (?, ?, ?, ?, 'RUNNING', CURRENT_TIMESTAMP) RETURNING sync_id",
                    Number.class, tenantId, projectId, userId, "MANUAL".equals(mode) ? "MANUAL" : "INCREMENTAL");
            syncId = created == null ? 0 : created.longValue();
            Map<String, Object> result = doSync(tenantId, userId, projectId, syncId);
            auditService.record(tenantId, userId, projectId, "SYNC", epoch(result.get("asOf")),
                    Collections.emptyList(), null, null);
            return result;
        } catch (RuntimeException ex) {
            if (syncId > 0) jdbcTemplate.update("UPDATE agent_project_document_sync SET status='FAILED', error_code=?, completed_at=CURRENT_TIMESTAMP WHERE sync_id=?", safeError(ex), syncId);
            auditService.record(tenantId, userId, projectId, "SYNC", null,
                    Collections.emptyList(), null, safeError(ex));
            throw ex;
        }
    }

    /**
     * 同步管理员配置的共享制度目录。
     * 参数 tenantId：租户；requestedByUserId：发起同步的 OA 用户，仅用于审计上下文。
     * 目录实际使用独立 KodCloud 只读服务账号，当前聊天用户不会获得目录外权限。
     */
    public Map<String, Object> syncPolicyLibrary(Long tenantId, Long requestedByUserId) {
        if (!bridgeService.hasPolicyLibrary(tenantId)) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("status", "NOT_CONFIGURED");
            result.put("scanned", 0);
            result.put("indexed", 0);
            result.put("invalidated", 0);
            return result;
        }
        Map<String, Object> visible = bridgeService.policyDocuments(tenantId);
        Set<Long> current = new LinkedHashSet<>();
        int scanned = 0, indexed = 0;
        for (Map<String, Object> item : maps(visible.get("items"))) {
            long fileId = number(item.get("fileID"));
            if (fileId <= 0) continue;
            current.add(fileId);
            scanned++;
            long sourceId = upsertPolicySource(tenantId, fileId, item);
            String name = String.valueOf(item.getOrDefault("name", ""));
            String ext = extension(name);
            if (!("txt".equals(ext) || "md".equals(ext) || "docx".equals(ext)
                    || "xlsx".equals(ext) || "pdf".equals(ext))) {
                updateSource(sourceId, "pdf".equals(ext) ? "NEEDS_OCR" : "UNSUPPORTED", null);
                continue;
            }
            try {
                String content = extractContent(bridgeService.policyDocument(tenantId, fileId), ext);
                if (!StringUtils.hasText(content)) {
                    updateSource(sourceId, emptyExtractionStatus(ext), null);
                    continue;
                }
                reindex(sourceId, name, sha256(content.getBytes(StandardCharsets.UTF_8)), content);
                indexed++;
            } catch (RuntimeException ex) {
                updateSource(sourceId, "FAILED", null);
            }
        }
        int invalidated = 0;
        List<Long> sources = jdbcTemplate.query(
                "SELECT source_id FROM agent_knowledge_source WHERE tenant_id=? "
                        + "AND source_type='POLICY_LIBRARY' AND invalidated_at IS NULL",
                (rs, rowNum) -> rs.getLong(1), tenantId);
        for (Long sourceId : sources) {
            Long fileId = jdbcTemplate.queryForObject(
                    "SELECT kod_file_id FROM agent_knowledge_source WHERE source_id=?", Long.class, sourceId);
            if (fileId != null && !current.contains(fileId)) {
                invalidateSource(sourceId);
                invalidated++;
            }
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "SUCCEEDED");
        result.put("scanned", scanned);
        result.put("indexed", indexed);
        result.put("invalidated", invalidated);
        result.put("asOf", OffsetDateTime.now());
        return result;
    }

    /**
     * 同步管理员维护的统一知识源。目录源以配置管理员身份建立索引；但其索引仅是
     * 派生副本，查询时仍会以当前提问用户身份重新枚举可见文件。
     */
    public Map<String, Object> syncManagedLibrary(Long tenantId, Long requestedByUserId, long libraryId) {
        Map<String, Object> library = libraryService.activeLibrary(tenantId, libraryId);
        try {
            Map<String, Object> result;
            String kind = String.valueOf(library.get("sourceKind"));
            if ("KOD_FOLDER".equals(kind)) {
                result = syncKodFolderLibrary(tenantId, library);
            } else if ("LOCAL_UPLOAD".equals(kind)) {
                result = syncLocalUploadLibrary(tenantId, library);
            } else {
                throw new IllegalArgumentException("知识源类型不支持");
            }
            libraryService.updateSyncStatus(tenantId, libraryId, "SUCCEEDED", null);
            return result;
        } catch (RuntimeException ex) {
            libraryService.updateSyncStatus(tenantId, libraryId, "FAILED", safeError(ex));
            throw ex;
        }
    }

    /** 停用来源时同步清除全文、chunk 与 embedding，不能让旧索引继续被检索。 */
    public void invalidateManagedLibrary(Long tenantId, long libraryId) {
        List<Long> sourceIds = jdbcTemplate.query("SELECT source_id FROM agent_knowledge_source "
                        + "WHERE tenant_id=? AND library_id=? AND invalidated_at IS NULL",
                (rs, rowNum) -> rs.getLong(1), tenantId, libraryId);
        for (Long sourceId : sourceIds) invalidateSource(sourceId);
    }

    private Map<String, Object> syncKodFolderLibrary(Long tenantId, Map<String, Object> library) {
        long libraryId = number(library.get("libraryId"));
        long ownerUserId = number(library.get("ownerUserId"));
        long folderId = number(library.get("folderId"));
        if (libraryId <= 0 || ownerUserId <= 0 || folderId <= 0) throw new IllegalStateException("知识目录配置无效");
        Map<String, Object> visible = bridgeService.knowledgeDocuments(tenantId, ownerUserId, folderId);
        Set<Long> current = new LinkedHashSet<>();
        int scanned = 0, indexed = 0;
        for (Map<String, Object> item : maps(visible.get("items"))) {
            long fileId = number(item.get("fileID"));
            if (fileId <= 0) continue;
            current.add(fileId); scanned++;
            long sourceId = upsertFolderSource(tenantId, libraryId, fileId, item);
            String name = String.valueOf(item.getOrDefault("name", ""));
            String ext = extension(name);
            if (!supportedExtension(ext)) {
                updateSource(sourceId, "pdf".equals(ext) ? "NEEDS_OCR" : "UNSUPPORTED", null);
                continue;
            }
            try {
                String content = extractContent(bridgeService.knowledgeDocument(tenantId, ownerUserId, folderId, fileId), ext);
                if (!StringUtils.hasText(content)) {
                    updateSource(sourceId, emptyExtractionStatus(ext), null);
                    continue;
                }
                reindex(sourceId, name, sha256(content.getBytes(StandardCharsets.UTF_8)), content);
                indexed++;
            } catch (RuntimeException ex) {
                updateSource(sourceId, "FAILED", null);
            }
        }
        int invalidated = invalidateMissingFolderSources(tenantId, libraryId, current);
        return managedSyncResult(libraryId, "KOD_FOLDER", scanned, indexed, invalidated);
    }

    private Map<String, Object> syncLocalUploadLibrary(Long tenantId, Map<String, Object> library) {
        long libraryId = number(library.get("libraryId"));
        Map<String, Object> upload = libraryService.upload(tenantId, libraryId);
        String name = String.valueOf(upload.getOrDefault("filename", ""));
        String ext = extension(name);
        long sourceId = upsertLocalUploadSource(tenantId, libraryId, upload);
        if (!supportedExtension(ext)) {
            updateSource(sourceId, "pdf".equals(ext) ? "NEEDS_OCR" : "UNSUPPORTED", null);
            return managedSyncResult(libraryId, "LOCAL_UPLOAD", 1, 0, 0);
        }
        String content = extractContent((byte[]) upload.get("content"), ext);
        if (!StringUtils.hasText(content)) {
            updateSource(sourceId, emptyExtractionStatus(ext), null);
            return managedSyncResult(libraryId, "LOCAL_UPLOAD", 1, 0, 0);
        }
        reindex(sourceId, name, sha256(content.getBytes(StandardCharsets.UTF_8)), content);
        return managedSyncResult(libraryId, "LOCAL_UPLOAD", 1, 1, 0);
    }

    private int invalidateMissingFolderSources(Long tenantId, long libraryId, Set<Long> current) {
        List<Map<String, Object>> sources = jdbcTemplate.query("SELECT source_id, kod_file_id FROM agent_knowledge_source "
                        + "WHERE tenant_id=? AND source_type='KOD_FOLDER' AND library_id=? AND invalidated_at IS NULL",
                (rs, rowNum) -> {
                    Map<String, Object> source = new LinkedHashMap<>();
                    source.put("sourceId", rs.getLong("source_id")); source.put("fileId", rs.getLong("kod_file_id"));
                    return source;
                }, tenantId, libraryId);
        int invalidated = 0;
        for (Map<String, Object> source : sources) {
            if (!current.contains(number(source.get("fileId")))) {
                invalidateSource(number(source.get("sourceId"))); invalidated++;
            }
        }
        return invalidated;
    }

    private static Map<String, Object> managedSyncResult(long libraryId, String sourceKind,
                                                          int scanned, int indexed, int invalidated) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("libraryId", libraryId); result.put("sourceKind", sourceKind); result.put("status", "SUCCEEDED");
        result.put("scanned", scanned); result.put("indexed", indexed); result.put("invalidated", invalidated);
        result.put("asOf", OffsetDateTime.now()); return result;
    }

    /**
     * 本地定时增量同步。
     *
     * <p>用户绑定只用于发现其可访问的项目，不能成为“同一项目同步次数”的
     * 乘数。同一轮中，多个成员看到同一个项目时只同步一次，并优先使用项目
     * 管理员身份：只有管理员看到的资料目录才能作为删除或失权索引的失效依据。
     * 普通成员只在没有任何管理员可用时兜底同步，此时 {@link #doSync} 会保守地
     * 跳过失效处理，避免把其他成员可见的资料错误标记为失效。</p>
     */
    @Scheduled(fixedDelayString = "${yudao.agent.project.sync-interval-ms:900000}")
    public void scheduledSync() {
        try {
            // 共享制度库使用独立服务账号同步，不依赖某个项目成员是否在线。
            List<Long> policyTenants = jdbcTemplate.query(
                    "SELECT tenant_id FROM agent_policy_library_binding WHERE status='ACTIVE'",
                    (rs, rowNum) -> rs.getLong(1));
            for (Long tenantId : policyTenants) {
                try {
                    syncPolicyLibrary(tenantId, null);
                } catch (RuntimeException ignored) {
                    // 单个租户制度库失败不阻断其他项目；下次定时任务继续重试。
                }
            }
            // 每个目录源仅同步一次，配置管理员是建立索引时的读取身份；查询路径不会
            // 复用该身份，因此不会把管理员的目录权限扩散给普通成员。
            for (Map<String, Object> library : libraryService.activeKodFolders()) {
                try {
                    syncManagedLibrary(numberObject(library.get("tenantId")), numberObject(library.get("ownerUserId")),
                            number(library.get("libraryId")));
                } catch (RuntimeException ignored) {
                    // 一个目录源失败不阻断其他目录和项目；状态由 library 记录安全错误码。
                }
            }
            List<Map<String, Object>> bindings = jdbcTemplate.query(
                    "SELECT tenant_id, oa_user_id FROM agent_kod_user_binding WHERE status='ACTIVE' "
                            + "ORDER BY tenant_id ASC, oa_user_id ASC",
                    (rs, rowNum) -> {
                        Map<String, Object> binding = new LinkedHashMap<>();
                        binding.put("tenantId", rs.getLong("tenant_id"));
                        binding.put("userId", rs.getLong("oa_user_id"));
                        return binding;
                    });
            Map<ProjectSyncKey, ProjectSyncTarget> targets = new LinkedHashMap<>();
            for (Map<String, Object> binding : bindings) {
                Long tenantId = (Long) binding.get("tenantId");
                Long userId = (Long) binding.get("userId");
                try {
                    Map<String, Object> projects = bridgeService.listProjects(tenantId, userId);
                    for (Map<String, Object> project : maps(projects.get("items"))) {
                        long projectId = number(project.get("projectID"));
                        if (projectId <= 0) continue;
                        collectScheduledTarget(targets, tenantId, projectId, userId, project.get("role"));
                    }
                } catch (RuntimeException ignored) {
                    // 单个用户/项目失败不能阻断其他项目的 15 分钟同步；失败原因已由
                    // 本次手动/增量记录保留在安全错误码字段中。
                }
            }
            for (ProjectSyncTarget target : targets.values()) {
                try {
                    syncProject(target.tenantId, target.oaUserId, target.projectId, "INCREMENTAL");
                } catch (RuntimeException ignored) {
                    // 一个项目同步失败不能阻断同一轮的其他项目；syncProject 已记录安全错误码。
                }
            }
        } catch (RuntimeException ignored) {
            // 首次迁移尚未完成时，定时任务应等待部署迁移，不得让后台线程刷异常正文。
        }
    }

    /**
     * 把一次“用户可见项目”发现结果收敛到本轮唯一同步目标。
     * 包可见是为了用纯单元测试覆盖管理员优先和同项目去重，无需启动定时线程。
     */
    static void collectScheduledTarget(Map<ProjectSyncKey, ProjectSyncTarget> targets,
                                       Long tenantId, long projectId, Long oaUserId, Object role) {
        if (tenantId == null || oaUserId == null || projectId <= 0) return;
        ProjectSyncTarget candidate = new ProjectSyncTarget(tenantId, projectId, oaUserId,
                "admin".equalsIgnoreCase(String.valueOf(role)));
        ProjectSyncKey key = new ProjectSyncKey(tenantId, projectId);
        ProjectSyncTarget current = targets.get(key);
        if (current == null || candidate.preferredOver(current)) targets.put(key, candidate);
    }

    /** 同一租户内的项目是资料索引和定时同步的唯一粒度。 */
    static final class ProjectSyncKey {
        final Long tenantId;
        final long projectId;

        ProjectSyncKey(Long tenantId, long projectId) {
            this.tenantId = tenantId;
            this.projectId = projectId;
        }

        @Override public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof ProjectSyncKey)) return false;
            ProjectSyncKey value = (ProjectSyncKey) other;
            return projectId == value.projectId && tenantId.equals(value.tenantId);
        }

        @Override public int hashCode() {
            return 31 * tenantId.hashCode() + (int) (projectId ^ (projectId >>> 32));
        }
    }

    /** 管理员优先；同级候选按用户编号稳定选择，保证每轮行为可复现。 */
    static final class ProjectSyncTarget {
        final Long tenantId;
        final long projectId;
        final Long oaUserId;
        final boolean administrator;

        ProjectSyncTarget(Long tenantId, long projectId, Long oaUserId, boolean administrator) {
            this.tenantId = tenantId;
            this.projectId = projectId;
            this.oaUserId = oaUserId;
            this.administrator = administrator;
        }

        boolean preferredOver(ProjectSyncTarget other) {
            if (administrator != other.administrator) return administrator;
            return oaUserId.compareTo(other.oaUserId) < 0;
        }
    }

    private Map<String, Object> doSync(Long tenantId, Long userId, long projectId, long syncId) {
        Map<String, Object> visible = bridgeService.documents(tenantId, userId, projectId);
        // 只有项目管理员能确认“当前目录中的全部文件”；普通成员的可见列表可能
        // 是权限子集，不能用它把其他成员的索引错误标记为失效。
        boolean canInvalidate = "admin".equalsIgnoreCase(String.valueOf(visible.get("role")));
        Set<Long> current = new LinkedHashSet<>();
        int scanned = 0, indexed = 0;
        for (Map<String, Object> item : maps(visible.get("items"))) {
            long fileId = number(item.get("fileID"));
            current.add(fileId);
            scanned++;
            long sourceId = upsertSource(tenantId, projectId, fileId, item);
            String name = String.valueOf(item.getOrDefault("name", ""));
            String ext = extension(name);
            if (!("txt".equals(ext) || "md".equals(ext) || "docx".equals(ext)
                    || "xlsx".equals(ext) || "pdf".equals(ext))) {
                updateSource(sourceId, "pdf".equals(ext) ? "NEEDS_OCR" : "UNSUPPORTED", null);
                continue;
            }
            String content;
            try {
                Map<String, Object> contentResult = bridgeService.document(tenantId, userId, projectId, fileId);
                content = extractContent(contentResult, ext);
            } catch (RuntimeException ex) {
                // 单个文件读取失败不能丢弃同一项目的其他资料；只记录安全错误状态。
                updateSource(sourceId, "FAILED", null);
                continue;
            }
            if (!StringUtils.hasText(content)) {
                updateSource(sourceId, emptyExtractionStatus(ext), null);
                continue;
            }
            String hash = sha256(content.getBytes(StandardCharsets.UTF_8));
            reindex(sourceId, name, hash, content);
            indexed++;
        }
        int invalidated = 0;
        List<Long> indexedSources = jdbcTemplate.query("SELECT source_id FROM agent_knowledge_source WHERE tenant_id=? AND source_type='PROJECT_FILES' AND project_id=? AND invalidated_at IS NULL", (rs, rowNum) -> rs.getLong(1), tenantId, projectId);
        for (Long sourceId : indexedSources) {
            Long fileId = jdbcTemplate.queryForObject("SELECT kod_file_id FROM agent_knowledge_source WHERE source_id=?", Long.class, sourceId);
            if (canInvalidate && fileId != null && !current.contains(fileId)) {
                invalidateSource(sourceId);
                invalidated++;
            }
        }
        jdbcTemplate.update("UPDATE agent_project_document_sync SET status='SUCCEEDED', scanned_count=?, indexed_count=?, invalidated_count=?, completed_at=CURRENT_TIMESTAMP WHERE sync_id=?", scanned, indexed, invalidated, syncId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("projectId", projectId); result.put("status", "SUCCEEDED");
        result.put("scanned", scanned); result.put("indexed", indexed); result.put("invalidated", invalidated);
        result.put("asOf", OffsetDateTime.now());
        return result;
    }

    /**
     * 失权或删除的资料不只是从来源表标记失效：其正文、chunk 和 embedding 都是
     * 可重建的派生副本，必须立即删除，避免异步 worker 在下一轮继续处理旧内容。
     */
    void invalidateSource(long sourceId) {
        jdbcTemplate.update("UPDATE agent_knowledge_source SET extraction_status='INVALIDATED', "
                + "invalidated_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE source_id=?", sourceId);
        jdbcTemplate.update("DELETE FROM agent_knowledge_document WHERE source_id=?", sourceId);
    }

    private long upsertSource(Long tenantId, long projectId, long fileId, Map<String, Object> file) {
        List<ExistingSource> sources = jdbcTemplate.query("SELECT source_id, content_version FROM agent_knowledge_source WHERE tenant_id=? AND source_type='PROJECT_FILES' AND project_id=? AND kod_file_id=?", (rs, rowNum) -> new ExistingSource(rs.getLong("source_id"), rs.getString("content_version")), tenantId, projectId, fileId);
        String name = String.valueOf(file.getOrDefault("name", "未命名资料"));
        String type = extension(name);
        String version = String.valueOf(file.getOrDefault("version", file.getOrDefault("contentHash", "")));
        if (sources.isEmpty()) {
            Number created = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_source (tenant_id, source_type, project_id, kod_file_id, display_name, document_type, content_version) VALUES (?, 'PROJECT_FILES', ?, ?, ?, ?, ?) RETURNING source_id", Number.class, tenantId, projectId, fileId, name, type, version);
            return created == null ? 0 : created.longValue();
        }
        ExistingSource source = sources.get(0);
        return prepareExistingSource(source.sourceId, source.contentVersion, name, type, version);
    }

    /** 制度来源没有 project_id，使用租户 + 文件编号保持幂等。 */
    private long upsertPolicySource(Long tenantId, long fileId, Map<String, Object> file) {
        List<ExistingSource> sources = jdbcTemplate.query(
                "SELECT source_id, content_version FROM agent_knowledge_source WHERE tenant_id=? "
                        + "AND source_type='POLICY_LIBRARY' AND kod_file_id=?",
                (rs, rowNum) -> new ExistingSource(rs.getLong("source_id"), rs.getString("content_version")), tenantId, fileId);
        String name = String.valueOf(file.getOrDefault("name", "未命名制度"));
        String type = extension(name);
        String version = String.valueOf(file.getOrDefault("version", file.getOrDefault("contentHash", "")));
        if (sources.isEmpty()) {
            Number created = jdbcTemplate.queryForObject(
                    "INSERT INTO agent_knowledge_source (tenant_id, source_type, kod_file_id, display_name, "
                            + "document_type, content_version) VALUES (?, 'POLICY_LIBRARY', ?, ?, ?, ?) RETURNING source_id",
                    Number.class, tenantId, fileId, name, type, version);
            return created == null ? 0 : created.longValue();
        }
        ExistingSource source = sources.get(0);
        return prepareExistingSource(source.sourceId, source.contentVersion, name, type, version);
    }

    private long upsertFolderSource(Long tenantId, long libraryId, long fileId, Map<String, Object> file) {
        List<ExistingSource> sources = jdbcTemplate.query("SELECT source_id, content_version FROM agent_knowledge_source WHERE tenant_id=? "
                        + "AND source_type='KOD_FOLDER' AND library_id=? AND kod_file_id=?",
                (rs, rowNum) -> new ExistingSource(rs.getLong("source_id"), rs.getString("content_version")), tenantId, libraryId, fileId);
        String name = String.valueOf(file.getOrDefault("name", "未命名资料"));
        String type = extension(name);
        String version = String.valueOf(file.getOrDefault("version", file.getOrDefault("contentHash", "")));
        if (sources.isEmpty()) {
            Number created = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_source "
                            + "(tenant_id, source_type, library_id, kod_file_id, display_name, document_type, content_version) "
                            + "VALUES (?, 'KOD_FOLDER', ?, ?, ?, ?, ?) RETURNING source_id",
                    Number.class, tenantId, libraryId, fileId, name, type, version);
            return created == null ? 0 : created.longValue();
        }
        ExistingSource source = sources.get(0);
        return prepareExistingSource(source.sourceId, source.contentVersion, name, type, version);
    }

    private long upsertLocalUploadSource(Long tenantId, long libraryId, Map<String, Object> upload) {
        List<ExistingSource> sources = jdbcTemplate.query("SELECT source_id, content_version FROM agent_knowledge_source WHERE tenant_id=? "
                        + "AND source_type='LOCAL_UPLOAD' AND library_id=?",
                (rs, rowNum) -> new ExistingSource(rs.getLong("source_id"), rs.getString("content_version")), tenantId, libraryId);
        String name = String.valueOf(upload.getOrDefault("filename", "未命名资料"));
        String type = extension(name);
        String version = String.valueOf(upload.getOrDefault("contentVersion", upload.getOrDefault("contentHash", "")));
        if (sources.isEmpty()) {
            Number created = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_source "
                            + "(tenant_id, source_type, library_id, display_name, document_type, content_version) "
                            + "VALUES (?, 'LOCAL_UPLOAD', ?, ?, ?, ?) RETURNING source_id",
                    Number.class, tenantId, libraryId, name, type, version);
            return created == null ? 0 : created.longValue();
        }
        ExistingSource source = sources.get(0);
        return prepareExistingSource(source.sourceId, source.contentVersion, name, type, version);
    }

    /**
     * 同步读取前先撤销来源的可检索资格。这样远端读取、提取或重建期间，搜索不会将
     * 旧 chunk 伪装成新版本；版本变更时立即级联删除旧 document/chunk/embedding。
     */
    long prepareExistingSource(long sourceId, String indexedVersion, String name, String type, String version) {
        boolean freshIndexRequired = requiresFreshIndex(indexedVersion, version);
        jdbcTemplate.update("UPDATE agent_knowledge_source SET display_name=?, document_type=?, content_version=?, "
                        + "extraction_status='PENDING', invalidated_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE source_id=?",
                name, type, version, sourceId);
        if (freshIndexRequired) {
            jdbcTemplate.update("DELETE FROM agent_knowledge_document WHERE source_id=?", sourceId);
        }
        return sourceId;
    }

    /** 元数据版本是同步前可用的唯一内容变更事实；不同版本绝不能复用旧派生索引。 */
    static boolean requiresFreshIndex(String indexedVersion, String incomingVersion) {
        return !String.valueOf(indexedVersion == null ? "" : indexedVersion)
                .equals(String.valueOf(incomingVersion == null ? "" : incomingVersion));
    }

    private void reindex(long sourceId, String name, String hash, String content) {
        String old = jdbcTemplate.query("SELECT content_hash FROM agent_knowledge_document WHERE source_id=? ORDER BY document_id DESC LIMIT 1", (rs, rowNum) -> rs.getString(1), sourceId).stream().findFirst().orElse(null);
        if (hash.equals(old)) { updateSource(sourceId, READY, hash); return; }
        jdbcTemplate.update("DELETE FROM agent_knowledge_document WHERE source_id=?", sourceId);
        Number documentId = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_document (source_id, title, content_hash, extraction_status) VALUES (?, ?, ?, 'READY') RETURNING document_id", Number.class, sourceId, name, hash);
        if (documentId == null) throw new IllegalStateException("知识文档写入失败");
        List<TextChunk> chunks = split(content);
        for (int i = 0; i < chunks.size(); i++) {
            TextChunk chunk = chunks.get(i);
            jdbcTemplate.update("INSERT INTO agent_knowledge_chunk (document_id, ordinal, section, content, content_hash) VALUES (?, ?, ?, ?, ?)",
                    documentId, i, chunk.section, chunk.content,
                    sha256(chunk.content.getBytes(StandardCharsets.UTF_8)));
        }
        updateSource(sourceId, READY, hash);
    }

    private void updateSource(long sourceId, String status, String hash) {
        jdbcTemplate.update("UPDATE agent_knowledge_source SET extraction_status=?, content_hash=COALESCE(?, content_hash), indexed_at=CASE WHEN ?='READY' THEN CURRENT_TIMESTAMP ELSE indexed_at END, updated_at=CURRENT_TIMESTAMP WHERE source_id=?", status, hash, status, sourceId);
    }

    private static final class ExistingSource {
        private final long sourceId;
        private final String contentVersion;

        private ExistingSource(long sourceId, String contentVersion) {
            this.sourceId = sourceId;
            this.contentVersion = contentVersion;
        }
    }

    private String extractContent(Map<String, Object> result, String ext) {
        String encoded = String.valueOf(result.getOrDefault("contentBase64", ""));
        if (!StringUtils.hasText(encoded)) return "";
        byte[] bytes;
        try { bytes = Base64.getDecoder().decode(encoded); } catch (IllegalArgumentException ex) { return ""; }
        return extractContent(bytes, ext);
    }

    private String extractContent(byte[] bytes, String ext) {
        if (bytes == null || bytes.length == 0) return "";
        if ("txt".equals(ext) || "md".equals(ext)) return new String(bytes, StandardCharsets.UTF_8);
        if ("pdf".equals(ext)) return pdfText(bytes);
        return xmlText(bytes);
    }

    private static String emptyExtractionStatus(String ext) {
        return "pdf".equals(ext) ? "NEEDS_OCR" : "UNSUPPORTED";
    }

    private static boolean supportedExtension(String ext) {
        return "txt".equals(ext) || "md".equals(ext) || "docx".equals(ext)
                || "xlsx".equals(ext) || "pdf".equals(ext);
    }

    /** 数字 PDF 按页提取，保留页码标记以便后续引用能返回稳定定位。 */
    private String pdfText(byte[] bytes) {
        try (PDDocument document = PDDocument.load(bytes)) {
            StringBuilder text = new StringBuilder();
            PDFTextStripper stripper = new PDFTextStripper();
            for (int page = 1; page <= document.getNumberOfPages(); page++) {
                stripper.setStartPage(page);
                stripper.setEndPage(page);
                String pageText = stripper.getText(document).replaceAll("\\s+", " ").trim();
                if (StringUtils.hasText(pageText)) text.append('\f').append("第 ").append(page)
                        .append(" 页\n").append(pageText).append('\n');
            }
            return text.toString().trim();
        } catch (IOException ex) {
            return "";
        }
    }

    /** DOCX/XLSX 都是 ZIP + XML；这里取文本节点，避免把工作簿 XML 结构当正文返回。 */
    private String xmlText(byte[] bytes) {
        StringBuilder text = new StringBuilder();
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (!entry.getName().endsWith(".xml")) continue;
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buffer = new byte[4096]; int count;
                while ((count = zip.read(buffer)) > 0) out.write(buffer, 0, count);
                String xml = new String(out.toByteArray(), StandardCharsets.UTF_8)
                        .replaceAll("<[^>]+>", " ").replaceAll("\\s+", " ").trim();
                if (StringUtils.hasText(xml)) text.append(xml).append('\n');
            }
        } catch (IOException ignored) { return ""; }
        return text.toString().trim();
    }

    private List<TextChunk> split(String content) {
        List<TextChunk> result = new ArrayList<>();
        for (int offset = 0; offset < content.length(); offset += CHUNK_SIZE) {
            int end = Math.min(content.length(), offset + CHUNK_SIZE);
            String chunk = content.substring(offset, end).replace("\f", "").trim();
            if (StringUtils.hasText(chunk)) result.add(new TextChunk(sectionAt(content, offset), chunk));
        }
        return result;
    }

    private String sectionAt(String content, int offset) {
        int marker = content.lastIndexOf('\f', offset);
        if (marker < 0) return "正文";
        int end = content.indexOf('\n', marker);
        String label = content.substring(marker + 1, end < 0 ? content.length() : end).trim();
        return StringUtils.hasText(label) ? label : "正文";
    }

    private static final class TextChunk {
        final String section;
        final String content;

        private TextChunk(String section, String content) {
            this.section = section;
            this.content = content;
        }
    }

    /**
     * 为没有中文分词扩展的 PostgreSQL 生成受控关键词集合。
     *
     * <p>连续中文片段会生成最长 8 字、最短 2 字的 n-gram；短语优先保留，随后剔除
     * 纯口语和泛化词。结果仅用于缩小当前已授权资料集合中的 SQL 候选范围，不能跨项目
     * 查询，也不会作为模型事实或执行参数。</p>
     */
    static List<String> keywordTerms(String query) {
        LinkedHashSet<String> collected = new LinkedHashSet<>();
        LinkedHashSet<String> intentTerms = new LinkedHashSet<>();
        if (!StringUtils.hasText(query)) return Collections.emptyList();
        addPlanningIntentTerms(intentTerms, query);
        Matcher cjk = CJK_RUN.matcher(query);
        while (cjk.find()) {
            addCjkTerms(collected, cjk.group());
        }
        Matcher latin = LATIN_TERM.matcher(query);
        while (latin.find()) {
            String term = latin.group().toLowerCase(Locale.ROOT);
            if (term.length() >= 2) collected.add(term);
        }
        List<String> terms = new ArrayList<>(collected);
        terms.sort(Comparator.comparingInt(String::length).reversed().thenComparing(Comparator.naturalOrder()));
        // 意图归一词不依赖 n-gram 长度，必须先保留；否则长自然问句会把“受阻”“责任人”
        // 等关键项目管理词挤出候选集合，退化回纯字面匹配。
        List<String> selected = new ArrayList<>(intentTerms);
        for (String term : terms) {
            if (selected.size() >= MAX_FALLBACK_TERMS) break;
            if (!selected.contains(term)) selected.add(term);
        }
        return selected;
    }

    /**
     * 将规划项目中高频、可解释的口语表达归一为资料与台账使用的稳定术语。
     *
     * <p>此表只覆盖“阻塞、责任、外发”三类调查意图，不承担开放式语义推断；每个
     * 扩展词都能直接在任务、风险台账或制度文件中被审计和回溯。</p>
     */
    private static void addPlanningIntentTerms(Set<String> target, String query) {
        String compact = query.replaceAll("[\\s，。！？、；：,.!?;:]+", "");
        if (compact.contains("卡住") || compact.contains("卡着") || compact.contains("停滞")
                || compact.contains("没进展") || compact.contains("没有进展")) {
            target.addAll(Arrays.asList("受阻", "待外部输入", "待核验", "未闭合", "风险"));
        }
        if (compact.contains("跟进") || compact.contains("负责") || compact.contains("谁来")
                || compact.contains("谁处理")) {
            target.addAll(Arrays.asList("责任人", "主责人", "下一步", "时限"));
        }
        if (compact.contains("外发") || compact.contains("对外") || compact.contains("保密")
                || (compact.contains("专家会") && compact.contains("材料"))) {
            target.addAll(Arrays.asList("外发材料", "版本核验", "保密核验", "脱敏"));
        }
    }

    private static void addCjkTerms(Set<String> target, String source) {
        String compact = source;
        for (String filler : QUERY_FILLERS) compact = compact.replace(filler, "");
        addCjkNgrams(target, source);
        if (!compact.equals(source)) addCjkNgrams(target, compact);
    }

    private static void addCjkNgrams(Set<String> target, String value) {
        if (value == null || value.length() < 2) return;
        int maximum = Math.min(8, value.length());
        for (int length = maximum; length >= 2; length--) {
            for (int offset = 0; offset + length <= value.length(); offset++) {
                String term = value.substring(offset, offset + length);
                if (!QUERY_FILLERS.contains(term)) target.add(term);
            }
        }
    }

    /** 按“标题命中 > 章节命中 > 最长正文短语 > 命中覆盖”排序，而不是依赖中文全文检索的零分结果。 */
    static List<Map<String, Object>> rankCandidates(List<Map<String, Object>> candidates,
                                                     List<String> terms, int limit) {
        List<Map<String, Object>> ranked = new ArrayList<>();
        for (Map<String, Object> candidate : candidates) {
            String name = String.valueOf(candidate.getOrDefault("name", "")).toLowerCase(Locale.ROOT);
            String section = String.valueOf(candidate.getOrDefault("section", "")).toLowerCase(Locale.ROOT);
            String content = String.valueOf(candidate.getOrDefault("content", "")).toLowerCase(Locale.ROOT);
            int titleLongest = 0, sectionLongest = 0, contentLongest = 0, coverage = 0;
            List<String> matched = new ArrayList<>();
            for (String term : terms) {
                String normalized = term.toLowerCase(Locale.ROOT);
                boolean titleMatch = name.contains(normalized);
                boolean sectionMatch = section.contains(normalized);
                boolean contentMatch = content.contains(normalized);
                if (!titleMatch && !sectionMatch && !contentMatch) continue;
                if (matched.size() < 6) matched.add(term);
                if (titleMatch) titleLongest = Math.max(titleLongest, term.length());
                if (sectionMatch) sectionLongest = Math.max(sectionLongest, term.length());
                if (contentMatch) {
                    contentLongest = Math.max(contentLongest, term.length());
                    coverage += term.length();
                }
            }
            double fullText = candidate.get("score") instanceof Number
                    ? ((Number) candidate.get("score")).doubleValue() : 0D;
            // n-gram 存在大量重叠，coverage 只作为小幅区分，最长短语才是主排序信号。
            double score = fullText + titleLongest * 10D + sectionLongest * 5D + contentLongest * 2D
                    + Math.min(60, coverage) / 100D;
            candidate.put("score", score);
            candidate.put("matchedTerms", matched);
            ranked.add(candidate);
        }
        ranked.sort((left, right) -> {
            int byScore = Double.compare(scoreNumber(right.get("score")), scoreNumber(left.get("score")));
            if (byScore != 0) return byScore;
            int byOrdinal = Long.compare(number(left.get("ordinal")), number(right.get("ordinal")));
            if (byOrdinal != 0) return byOrdinal;
            return Long.compare(number(left.get("chunkId")), number(right.get("chunkId")));
        });
        return new ArrayList<>(ranked.subList(0, Math.min(Math.max(1, limit), ranked.size())));
    }

    /**
     * 以 RRF 合并全文与语义候选。全文分保留标题/术语优势，避免项目编号、文件名和
     * 专有名词被相似语义片段盖过；语义分只影响候选覆盖范围，不改变权限范围。
     */
    static List<Map<String, Object>> mergeHybridCandidates(List<Map<String, Object>> lexical,
                                                             List<Map<String, Object>> semantic,
                                                             int limit) {
        Map<Long, HybridCandidate> candidates = new LinkedHashMap<>();
        mergeRanked(candidates, lexical, true);
        mergeRanked(candidates, semantic, false);
        List<Map<String, Object>> ranked = new ArrayList<>();
        for (HybridCandidate candidate : candidates.values()) ranked.add(candidate.toMap());
        ranked.sort((left, right) -> {
            int byFusion = Double.compare(scoreNumber(right.get("fusionScore")), scoreNumber(left.get("fusionScore")));
            if (byFusion != 0) return byFusion;
            int byLexical = Double.compare(scoreNumber(right.get("keywordScore")), scoreNumber(left.get("keywordScore")));
            if (byLexical != 0) return byLexical;
            int bySemantic = Double.compare(scoreNumber(right.get("semanticScore")), scoreNumber(left.get("semanticScore")));
            if (bySemantic != 0) return bySemantic;
            int byOrdinal = Long.compare(number(left.get("ordinal")), number(right.get("ordinal")));
            if (byOrdinal != 0) return byOrdinal;
            return Long.compare(number(left.get("chunkId")), number(right.get("chunkId")));
        });
        return new ArrayList<>(ranked.subList(0, Math.min(Math.max(1, limit), ranked.size())));
    }

    private static void mergeRanked(Map<Long, HybridCandidate> target, List<Map<String, Object>> values,
                                    boolean keyword) {
        if (values == null) return;
        for (int index = 0; index < values.size(); index++) {
            Map<String, Object> source = values.get(index);
            long chunkId = number(source.get("chunkId"));
            if (chunkId <= 0) continue;
            HybridCandidate candidate = target.computeIfAbsent(chunkId, ignored -> new HybridCandidate(source));
            int rank = index + 1;
            if (keyword) candidate.keyword(source, rank);
            else candidate.semantic(source, rank);
        }
    }

    /** 将内部候选投影成可展示、可核验而不泄露全文的资料证据。 */
    static Map<String, Object> evidence(Map<String, Object> candidate, int ordinal) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("citationId", "资料 " + ordinal);
        result.put("chunkId", candidate.get("chunkId"));
        result.put("sourceType", candidate.get("sourceType"));
        result.put("projectId", candidate.get("projectId"));
        result.put("libraryId", candidate.get("libraryId"));
        result.put("fileId", candidate.get("fileId"));
        result.put("name", candidate.get("name"));
        result.put("documentType", candidate.get("documentType"));
        result.put("contentVersion", candidate.get("contentVersion"));
        result.put("section", candidate.getOrDefault("section", "正文"));
        result.put("ordinal", candidate.get("ordinal"));
        result.put("excerpt", excerpt(String.valueOf(candidate.getOrDefault("content", ""))));
        result.put("retrievalMethod", candidate.getOrDefault("retrievalMethod", "keyword"));
        result.put("fusionScore", scoreNumber(candidate.get("fusionScore")));
        if (candidate.get("matchedTerms") instanceof List) result.put("matchedTerms", candidate.get("matchedTerms"));
        return result;
    }

    private static String excerpt(String content) {
        String normalized = content.replaceAll("\\s+", " ").trim();
        return normalized.length() <= 280 ? normalized : normalized.substring(0, 279) + "…";
    }

    private static final class HybridCandidate {
        private final Map<String, Object> values;
        private int keywordRank;
        private int semanticRank;
        private double fusionScore;

        private HybridCandidate(Map<String, Object> source) {
            this.values = new LinkedHashMap<>(source);
        }

        private void keyword(Map<String, Object> source, int rank) {
            keywordRank = rank;
            fusionScore += reciprocalRank(rank);
            values.put("keywordRank", rank);
            values.put("keywordScore", scoreNumber(source.get("score")));
            copyIfPresent(source, "matchedTerms");
        }

        private void semantic(Map<String, Object> source, int rank) {
            semanticRank = rank;
            fusionScore += reciprocalRank(rank);
            values.put("semanticRank", rank);
            values.put("semanticScore", scoreNumber(source.get("semanticScore")));
        }

        private Map<String, Object> toMap() {
            values.put("fusionScore", fusionScore);
            values.put("retrievalMethod", keywordRank > 0 && semanticRank > 0 ? "hybrid"
                    : (keywordRank > 0 ? "keyword" : "semantic"));
            return values;
        }

        private void copyIfPresent(Map<String, Object> source, String key) {
            if (source.containsKey(key)) values.put(key, source.get(key));
        }

        private static double reciprocalRank(int rank) {
            return 1D / (RRF_K + rank);
        }
    }

    private static String likePattern(String term) {
        return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%";
    }

    private static double scoreNumber(Object value) {
        return value instanceof Number ? ((Number) value).doubleValue() : 0D;
    }

    /** 只保留本次项目目录中仍可见且版本未变化的项目资料；制度库不受项目文件版本影响。 */
    static List<Map<String, Object>> currentSources(List<Map<String, Object>> sources,
                                                     Map<Long, String> visibleVersions) {
        List<Map<String, Object>> current = new ArrayList<>();
        for (Map<String, Object> source : sources) {
            if (!"PROJECT_FILES".equals(source.get("sourceType"))) {
                current.add(source);
                continue;
            }
            long fileId = number(source.get("fileId"));
            String visibleVersion = visibleVersions.get(fileId);
            String indexedVersion = String.valueOf(source.getOrDefault("contentVersion", ""));
            if (StringUtils.hasText(visibleVersion) && visibleVersion.equals(indexedVersion)) current.add(source);
        }
        return current;
    }

    /** 目录源的 fileId 只在同一 libraryId 内有意义，必须同时核对库、文件与版本。 */
    static List<Map<String, Object>> currentFolderSources(List<Map<String, Object>> sources,
                                                           Map<Long, Map<Long, String>> folderVersions) {
        List<Map<String, Object>> current = new ArrayList<>();
        for (Map<String, Object> source : sources) {
            if (!"KOD_FOLDER".equals(source.get("sourceType"))
                    || visibleFolderSource(source, folderVersions.get(number(source.get("libraryId"))))) {
                current.add(source);
            }
        }
        return current;
    }

    static boolean visibleFolderSource(Map<String, Object> source, Map<Long, String> visibleVersions) {
        if (visibleVersions == null || visibleVersions.isEmpty()) return false;
        long fileId = number(source.get("fileId"));
        String current = visibleVersions.get(fileId);
        String indexed = String.valueOf(source.getOrDefault("contentVersion", ""));
        return fileId > 0 && StringUtils.hasText(current) && current.equals(indexed);
    }

    private Map<String, Object> result(String query, String mode, List<Map<String, Object>> hits, Object asOf) {
        Map<String, Object> result = new LinkedHashMap<>(); result.put("query", query); result.put("retrievalMode", mode); result.put("hits", hits); result.put("total", hits.size()); result.put("asOf", asOf == null ? OffsetDateTime.now() : asOf); return result;
    }
    private static String retrievalMode(AgentProjectEmbeddingService.RetrievalMode configuredMode,
                                        AgentProjectEmbeddingService.SemanticSearch semantic,
                                        boolean ragRequested) {
        if (configuredMode == AgentProjectEmbeddingService.RetrievalMode.KEYWORD || !ragRequested) return "keyword";
        if (!semantic.available) return "keyword_fallback";
        return configuredMode == AgentProjectEmbeddingService.RetrievalMode.SEMANTIC ? "semantic" : "hybrid";
    }
    static Map<String, Object> retrievalAuditMetadata(String mode, int keywordCandidates, int semanticCandidates,
                                                       int returnedEvidence, int permissionFiltered,
                                                       boolean vectorAvailable, String vectorFailureCode,
                                                       long elapsedMs) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("retrievalMode", mode);
        metadata.put("keywordCandidateCount", Math.max(0, keywordCandidates));
        metadata.put("semanticCandidateCount", Math.max(0, semanticCandidates));
        metadata.put("returnedEvidenceCount", Math.max(0, returnedEvidence));
        metadata.put("permissionFilteredCount", Math.max(0, permissionFiltered));
        boolean notRequested = "KEYWORD_MODE".equals(vectorFailureCode) || "NOT_REQUESTED".equals(vectorFailureCode);
        metadata.put("vectorState", vectorAvailable ? "READY" : (notRequested ? "NOT_REQUESTED" : "UNAVAILABLE"));
        if (!vectorAvailable && !notRequested && StringUtils.hasText(vectorFailureCode)) {
            metadata.put("vectorFailureCode", vectorFailureCode);
        }
        metadata.put("elapsedMs", Math.max(0L, elapsedMs));
        return metadata;
    }
    private static long elapsedMillis(long startedAtNanos) {
        return TimeUnit.NANOSECONDS.toMillis(Math.max(0L, System.nanoTime() - startedAtNanos));
    }

    private String safeError(RuntimeException ex) { return ex.getClass().getSimpleName().replaceAll("[^A-Za-z0-9_]", "_"); }
    private static Long epoch(Object value) {
        if (value instanceof Number) return ((Number) value).longValue();
        try { return value == null ? null : Long.parseLong(String.valueOf(value)); }
        catch (RuntimeException ignored) { return null; }
    }
    private static List<Map<String, Object>> sourceVersions(List<Map<String, Object>> sources) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> source : sources) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sourceId", source.get("sourceId"));
            item.put("sourceType", source.get("sourceType"));
            item.put("projectId", source.get("projectId"));
            item.put("libraryId", source.get("libraryId"));
            item.put("fileId", source.get("fileId"));
            item.put("name", source.get("name"));
            result.add(item);
        }
        return result;
    }
    private static long number(Object value) { try { return Long.parseLong(String.valueOf(value)); } catch (RuntimeException ex) { return 0; } }
    private static Long numberObject(Object value) { long result = number(value); return result > 0 ? result : null; }
    private static String extension(String name) { int dot = name.lastIndexOf('.'); return dot < 0 ? "" : name.substring(dot + 1).toLowerCase(); }
    private static String sha256(byte[] value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(value);
            StringBuilder hex = new StringBuilder(digest.length * 2);
            for (byte item : digest) hex.append(String.format(Locale.ROOT, "%02x", item & 0xFF));
            return hex.toString();
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }
    @SuppressWarnings("unchecked") private static List<Map<String, Object>> maps(Object value) { if (!(value instanceof List)) return Collections.emptyList(); List<Map<String, Object>> out = new ArrayList<>(); for (Object item : (List<?>) value) if (item instanceof Map) out.add((Map<String, Object>) item); return out; }
}
