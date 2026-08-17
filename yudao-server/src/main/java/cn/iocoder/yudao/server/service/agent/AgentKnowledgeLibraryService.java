package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 管理员维护的通用知识源配置和本地上传受控存储。
 *
 * <p>本服务只维护来源配置、上传二进制和 ACL；KodCloud 目录的实际文件清单与
 * 读取权限始终由桥接层在同步/检索时复核，不能把本表视为文件授权事实。</p>
 */
@Service
public class AgentKnowledgeLibraryService {

    private static final Set<String> SUPPORTED_EXTENSIONS = Collections.unmodifiableSet(
            new LinkedHashSet<>(Arrays.asList("pdf", "docx", "xlsx", "txt", "md")));
    private static final Set<String> GENERIC_UPLOAD_MIME_TYPES = Collections.unmodifiableSet(
            new LinkedHashSet<>(Arrays.asList("", "application/octet-stream")));
    private static final long MAX_UPLOAD_BYTES = 20L * 1024L * 1024L;
    private static final String LOCAL_UPLOAD_ACCESS_PREDICATE = "(l.access_mode='ALL' OR "
            + "(l.access_mode='CUSTOM' AND ((acl.subject_type='USER' AND acl.subject_id=?) "
            + "OR (acl.subject_type='DEPARTMENT' AND acl.subject_id=?))))";

    @Resource
    @Qualifier("agentEventJdbcTemplate")
    private JdbcTemplate jdbcTemplate;
    @Resource
    private AdminUserService adminUserService;

    public Map<String, Object> createKodFolder(Long tenantId, Long ownerUserId, String name, long folderId) {
        if (tenantId == null || ownerUserId == null || folderId <= 0) {
            throw new IllegalArgumentException("知识目录缺少租户、管理员或目录编号");
        }
        String displayName = requiredName(name, "KodCloud 目录");
        Number value = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_library "
                        + "(tenant_id, name, source_kind, kod_folder_id, owner_user_id, access_mode, status) "
                        + "VALUES (?, ?, 'KOD_FOLDER', ?, ?, 'FOLDER', 'ACTIVE') RETURNING library_id",
                Number.class, tenantId, displayName, folderId, ownerUserId);
        return library(tenantId, value.longValue());
    }

    @Transactional(transactionManager = "agentEventTransactionManager", rollbackFor = Exception.class)
    public Map<String, Object> createLocalUpload(Long tenantId, Long ownerUserId, String name,
                                                  String filename, String mimeType, byte[] content,
                                                  String accessMode, List<AclSubject> acl) {
        if (tenantId == null || ownerUserId == null) throw new IllegalArgumentException("上传资料缺少租户或管理员");
        if (content == null || content.length == 0 || content.length > MAX_UPLOAD_BYTES) {
            throw new IllegalArgumentException("上传文件不能为空且不能超过 20 MB");
        }
        String safeFilename = requiredFilename(filename);
        if (!SUPPORTED_EXTENSIONS.contains(extension(safeFilename))) {
            throw new IllegalArgumentException("仅支持 PDF、DOCX、XLSX、TXT、Markdown 文件");
        }
        validateMimeType(safeFilename, mimeType);
        String normalizedAccess = text(accessMode).toUpperCase(Locale.ROOT);
        if (!validAccessMode("LOCAL_UPLOAD", normalizedAccess)) {
            throw new IllegalArgumentException("本地上传资料的访问范围无效");
        }
        List<AclSubject> normalizedAcl = normalizeAcl(acl);
        if ("CUSTOM".equals(normalizedAccess) && normalizedAcl.isEmpty()) {
            throw new IllegalArgumentException("指定范围至少需要选择一个部门或人员");
        }
        if ("ALL".equals(normalizedAccess)) normalizedAcl = Collections.emptyList();
        String displayName = requiredName(name, stripExtension(safeFilename));
        Number value = jdbcTemplate.queryForObject("INSERT INTO agent_knowledge_library "
                        + "(tenant_id, name, source_kind, owner_user_id, access_mode, status) "
                        + "VALUES (?, ?, 'LOCAL_UPLOAD', ?, ?, 'ACTIVE') RETURNING library_id",
                Number.class, tenantId, displayName, ownerUserId, normalizedAccess);
        long libraryId = value.longValue();
        String hash = sha256(content);
        jdbcTemplate.update("INSERT INTO agent_knowledge_upload "
                        + "(library_id, filename, mime_type, content_data, content_hash, content_version, size_bytes) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?)",
                libraryId, safeFilename, text(mimeType, "application/octet-stream"), content, hash, hash, content.length);
        insertAcl(libraryId, normalizedAcl);
        return library(tenantId, libraryId);
    }

    public List<Map<String, Object>> list(Long tenantId) {
        if (tenantId == null) return Collections.emptyList();
        return jdbcTemplate.query("SELECT l.library_id, l.name, l.source_kind, l.kod_folder_id, l.owner_user_id, "
                        + "l.access_mode, l.status, l.last_sync_at, l.last_sync_status, l.last_error_code, l.created_at, "
                        + "COUNT(s.source_id) FILTER (WHERE s.invalidated_at IS NULL) AS document_count, "
                        + "COUNT(s.source_id) FILTER (WHERE s.extraction_status='READY' AND s.invalidated_at IS NULL) AS ready_count "
                        + "FROM agent_knowledge_library l LEFT JOIN agent_knowledge_source s ON s.library_id=l.library_id "
                        + "WHERE l.tenant_id=? GROUP BY l.library_id ORDER BY l.updated_at DESC, l.library_id DESC",
                (rs, rowNum) -> libraryRow(rs), tenantId);
    }

    public Map<String, Object> library(Long tenantId, long libraryId) {
        List<Map<String, Object>> rows = jdbcTemplate.query("SELECT l.library_id, l.name, l.source_kind, l.kod_folder_id, "
                        + "l.owner_user_id, l.access_mode, l.status, l.last_sync_at, l.last_sync_status, l.last_error_code, l.created_at, "
                        + "COUNT(s.source_id) FILTER (WHERE s.invalidated_at IS NULL) AS document_count, "
                        + "COUNT(s.source_id) FILTER (WHERE s.extraction_status='READY' AND s.invalidated_at IS NULL) AS ready_count "
                        + "FROM agent_knowledge_library l LEFT JOIN agent_knowledge_source s ON s.library_id=l.library_id "
                        + "WHERE l.tenant_id=? AND l.library_id=? GROUP BY l.library_id",
                (rs, rowNum) -> libraryRow(rs), tenantId, libraryId);
        if (rows.isEmpty()) throw new IllegalArgumentException("知识源不存在或不属于当前租户");
        return rows.get(0);
    }

    public Map<String, Object> activeLibrary(Long tenantId, long libraryId) {
        Map<String, Object> library = library(tenantId, libraryId);
        if (!"ACTIVE".equals(library.get("status"))) throw new IllegalStateException("知识源已停用");
        return library;
    }

    public void disable(Long tenantId, long libraryId) {
        int changed = jdbcTemplate.update("UPDATE agent_knowledge_library SET status='DISABLED', updated_at=CURRENT_TIMESTAMP "
                + "WHERE tenant_id=? AND library_id=? AND status='ACTIVE'", tenantId, libraryId);
        if (changed == 0) library(tenantId, libraryId);
    }

    public void updateSyncStatus(Long tenantId, long libraryId, String status, String errorCode) {
        jdbcTemplate.update("UPDATE agent_knowledge_library SET last_sync_at=CURRENT_TIMESTAMP, last_sync_status=?, "
                        + "last_error_code=?, updated_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND library_id=?",
                text(status, "FAILED"), errorCode, tenantId, libraryId);
    }

    public List<Map<String, Object>> activeKodFolders() {
        return jdbcTemplate.query("SELECT library_id, tenant_id, owner_user_id, kod_folder_id FROM agent_knowledge_library "
                        + "WHERE source_kind='KOD_FOLDER' AND status='ACTIVE' ORDER BY library_id",
                (rs, rowNum) -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("libraryId", rs.getLong("library_id"));
                    item.put("tenantId", rs.getLong("tenant_id"));
                    item.put("ownerUserId", rs.getLong("owner_user_id"));
                    item.put("folderId", rs.getLong("kod_folder_id"));
                    return item;
                });
    }

    public List<Long> visibleLocalLibraryIds(Long tenantId, Long userId) {
        if (tenantId == null || userId == null) return Collections.emptyList();
        AdminUserDO user = adminUserService.getUser(userId);
        Long deptId = user == null ? null : user.getDeptId();
        List<Object> args = new ArrayList<>();
        args.add(tenantId); args.add(userId); args.add(deptId == null ? -1L : deptId);
        return jdbcTemplate.query("SELECT DISTINCT l.library_id FROM agent_knowledge_library l "
                        + "LEFT JOIN agent_knowledge_library_acl acl ON acl.library_id=l.library_id "
                        + "WHERE l.tenant_id=? AND l.status='ACTIVE' AND l.source_kind='LOCAL_UPLOAD' "
                        + "AND " + LOCAL_UPLOAD_ACCESS_PREDICATE + " "
                        + "ORDER BY l.library_id",
                (rs, rowNum) -> rs.getLong(1), args.toArray());
    }

    /**
     * 本地上传资料的唯一读取授权判断。
     *
     * <p>部门 ACL 只比对 {@link AdminUserDO#getDeptId()} 返回的直属部门，不沿部门树
     * 递归扩大范围。来源索引和聊天历史都不能代替此判断；调用方必须在读取上传二进制
     * 或返回检索证据前再次使用本方法。</p>
     */
    public boolean canReadLocalLibrary(Long tenantId, Long userId, long libraryId) {
        if (tenantId == null || userId == null || libraryId <= 0) return false;
        AdminUserDO user = adminUserService.getUser(userId);
        if (user == null) return false;
        Long directDeptId = user.getDeptId();
        Boolean allowed = jdbcTemplate.queryForObject(
                "SELECT EXISTS (SELECT 1 FROM agent_knowledge_library l "
                        + "LEFT JOIN agent_knowledge_library_acl acl ON acl.library_id=l.library_id "
                        + "WHERE l.tenant_id=? AND l.library_id=? AND l.status='ACTIVE' "
                        + "AND l.source_kind='LOCAL_UPLOAD' AND " + LOCAL_UPLOAD_ACCESS_PREDICATE + ")",
                Boolean.class, tenantId, libraryId, userId, directDeptId == null ? -1L : directDeptId);
        return Boolean.TRUE.equals(allowed);
    }

    public Map<String, Object> upload(Long tenantId, long libraryId) {
        List<Map<String, Object>> rows = jdbcTemplate.query("SELECT u.filename, u.mime_type, u.content_data, u.content_hash, u.content_version, u.size_bytes "
                        + "FROM agent_knowledge_upload u JOIN agent_knowledge_library l ON l.library_id=u.library_id "
                        + "WHERE u.library_id=? AND l.tenant_id=?",
                (rs, rowNum) -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("filename", rs.getString("filename"));
                    item.put("mimeType", rs.getString("mime_type"));
                    item.put("content", rs.getBytes("content_data"));
                    item.put("contentHash", rs.getString("content_hash"));
                    item.put("contentVersion", rs.getString("content_version"));
                    item.put("size", rs.getLong("size_bytes"));
                    return item;
                }, libraryId, tenantId);
        if (rows.isEmpty()) throw new IllegalStateException("上传知识源的受控文件不存在");
        return rows.get(0);
    }

    public static boolean validAccessMode(String sourceKind, String accessMode) {
        String kind = text(sourceKind).toUpperCase(Locale.ROOT);
        String mode = text(accessMode).toUpperCase(Locale.ROOT);
        return "KOD_FOLDER".equals(kind) ? "FOLDER".equals(mode)
                : "LOCAL_UPLOAD".equals(kind) && ("ALL".equals(mode) || "CUSTOM".equals(mode));
    }

    static boolean allowsLocalRead(String accessMode, Long userId, Long deptId, List<AclSubject> acl) {
        if ("ALL".equalsIgnoreCase(text(accessMode))) return true;
        if (!"CUSTOM".equalsIgnoreCase(text(accessMode)) || userId == null) return false;
        for (AclSubject item : acl == null ? Collections.<AclSubject>emptyList() : acl) {
            if ("USER".equals(item.subjectType) && userId.equals(item.subjectId)) return true;
            if ("DEPARTMENT".equals(item.subjectType) && deptId != null && deptId.equals(item.subjectId)) return true;
        }
        return false;
    }

    private void insertAcl(long libraryId, List<AclSubject> acl) {
        for (AclSubject item : acl) {
            jdbcTemplate.update("INSERT INTO agent_knowledge_library_acl (library_id, subject_type, subject_id) "
                    + "VALUES (?, ?, ?) ON CONFLICT DO NOTHING", libraryId, item.subjectType, item.subjectId);
        }
    }

    private static List<AclSubject> normalizeAcl(List<AclSubject> values) {
        LinkedHashSet<AclSubject> result = new LinkedHashSet<>();
        if (values != null) for (AclSubject item : values) {
            if (item == null || item.subjectId == null || item.subjectId <= 0) {
                throw new IllegalArgumentException("访问范围包含无效的部门或人员");
            }
            String type = text(item.subjectType).toUpperCase(Locale.ROOT);
            if (!("USER".equals(type) || "DEPARTMENT".equals(type))) {
                throw new IllegalArgumentException("访问范围类型仅支持部门或人员");
            }
            result.add(new AclSubject(type, item.subjectId));
        }
        return new ArrayList<>(result);
    }

    private static Map<String, Object> libraryRow(java.sql.ResultSet rs) throws java.sql.SQLException {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("libraryId", rs.getLong("library_id")); item.put("name", rs.getString("name"));
        item.put("sourceKind", rs.getString("source_kind")); item.put("folderId", rs.getObject("kod_folder_id"));
        item.put("ownerUserId", rs.getLong("owner_user_id")); item.put("accessMode", rs.getString("access_mode"));
        item.put("status", rs.getString("status")); item.put("lastSyncAt", rs.getObject("last_sync_at"));
        item.put("lastSyncStatus", rs.getString("last_sync_status")); item.put("lastErrorCode", rs.getString("last_error_code"));
        item.put("createdAt", rs.getObject("created_at")); item.put("documentCount", rs.getLong("document_count"));
        item.put("readyCount", rs.getLong("ready_count")); return item;
    }

    private static String requiredName(String value, String fallback) {
        String name = text(value, fallback).trim();
        if (!StringUtils.hasText(name) || name.length() > 200) throw new IllegalArgumentException("知识源名称不能为空且最多 200 个字符");
        return name;
    }
    private static String requiredFilename(String value) {
        String filename = text(value).replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        if (!StringUtils.hasText(filename) || filename.length() > 500) throw new IllegalArgumentException("上传文件名无效");
        return filename;
    }
    private static void validateMimeType(String filename, String mimeType) {
        String normalized = text(mimeType).trim().toLowerCase(Locale.ROOT);
        int parameters = normalized.indexOf(';');
        if (parameters >= 0) normalized = normalized.substring(0, parameters).trim();
        if (GENERIC_UPLOAD_MIME_TYPES.contains(normalized)) return;
        String ext = extension(filename);
        boolean matches = ("pdf".equals(ext) && "application/pdf".equals(normalized))
                || ("docx".equals(ext) && "application/vnd.openxmlformats-officedocument.wordprocessingml.document".equals(normalized))
                || ("xlsx".equals(ext) && "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".equals(normalized))
                || ("txt".equals(ext) && "text/plain".equals(normalized))
                || ("md".equals(ext) && ("text/markdown".equals(normalized) || "text/plain".equals(normalized)));
        if (!matches) throw new IllegalArgumentException("文件扩展名与内容类型不一致");
    }
    private static String extension(String value) { int dot = value.lastIndexOf('.'); return dot < 0 ? "" : value.substring(dot + 1).toLowerCase(Locale.ROOT); }
    private static String stripExtension(String value) { int dot = value.lastIndexOf('.'); return dot <= 0 ? value : value.substring(0, dot); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
    private static String text(Object value, String fallback) { String text = text(value); return StringUtils.hasText(text) ? text : fallback; }
    private static String sha256(byte[] bytes) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
            StringBuilder out = new StringBuilder(hash.length * 2);
            for (byte value : hash) out.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            return out.toString();
        } catch (Exception ex) { throw new IllegalStateException("上传资料哈希计算失败", ex); }
    }

    public static final class AclSubject {
        final String subjectType;
        final Long subjectId;
        public AclSubject(String subjectType, Long subjectId) { this.subjectType = subjectType; this.subjectId = subjectId; }
        @Override public boolean equals(Object other) {
            if (!(other instanceof AclSubject)) return false;
            AclSubject value = (AclSubject) other;
            return subjectType.equals(value.subjectType) && subjectId.equals(value.subjectId);
        }
        @Override public int hashCode() { return 31 * subjectType.hashCode() + subjectId.hashCode(); }
    }
}
