package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import cn.iocoder.yudao.server.service.agent.AgentKnowledgeLibraryService;
import cn.iocoder.yudao.server.service.agent.AgentProjectKnowledgeService;
import cn.iocoder.yudao.server.service.agent.KodProjectBridgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/** 管理员的统一知识源管理 API。浏览器始终经 Next.js 代理携带当前 OA 身份。 */
@Tag(name = "Business Agent Knowledge Administration")
@RestController
@RequestMapping("/admin-api/agent/knowledge-libraries")
public class AgentKnowledgeAdminController {

    @Resource private AgentKnowledgeLibraryService libraryService;
    @Resource private AgentProjectKnowledgeService knowledgeService;
    @Resource private KodProjectBridgeService bridgeService;
    @Resource private AdminUserService adminUserService;
    @Resource @Qualifier("agentEventJdbcTemplate") private JdbcTemplate jdbcTemplate;

    @GetMapping
    @Operation(summary = "列出当前租户的知识源")
    public List<Map<String, Object>> list() {
        return libraryService.list(getTenantId());
    }

    /**
     * 受控 KodCloud 目录浏览。folderId 为空时返回当前管理员的个人根目录；用户可用
     * 已知目录编号跳转，但每次都会由 KodCloud explorer.auth 校验权限。
     */
    @GetMapping("/kod-folders/browse")
    @Operation(summary = "浏览当前管理员可读的 KodCloud 目录")
    public Map<String, Object> browseKodFolder(@RequestParam(value = "folderId", required = false) Long folderId) {
        return bridgeService.knowledgeFolder(getTenantId(), getLoginUserId(), positiveOrNull(folderId));
    }

    @PostMapping("/kod-folders")
    @Operation(summary = "添加 KodCloud 目录知识源")
    public Map<String, Object> createKodFolder(@RequestBody Map<String, Object> request) {
        long folderId = positive(number(request == null ? null : request.get("folderId")));
        // 在落库前先以当前配置管理员身份校验目录；不能允许管理员把无权目录写成来源。
        bridgeService.knowledgeFolder(getTenantId(), getLoginUserId(), folderId);
        Map<String, Object> library = libraryService.createKodFolder(getTenantId(), getLoginUserId(),
                text(request == null ? null : request.get("name")), folderId);
        Map<String, Object> result = new LinkedHashMap<>(library);
        result.put("sync", syncResult(number(library.get("libraryId"))));
        return result;
    }

    @PostMapping(value = "/uploads", consumes = "multipart/form-data")
    @Operation(summary = "上传本地知识资料并设置访问范围")
    public Map<String, Object> upload(@RequestPart("file") MultipartFile file,
                                      @RequestParam(value = "name", required = false) String name,
                                      @RequestParam(value = "accessMode", defaultValue = "ALL") String accessMode,
                                      @RequestParam(value = "userIds", required = false) List<Long> userIds,
                                      @RequestParam(value = "departmentIds", required = false) List<Long> departmentIds) throws Exception {
        List<AgentKnowledgeLibraryService.AclSubject> acl = new ArrayList<>();
        for (Long id : userIds == null ? Collections.<Long>emptyList() : userIds) {
            if (id != null && id > 0) acl.add(new AgentKnowledgeLibraryService.AclSubject("USER", id));
        }
        for (Long id : departmentIds == null ? Collections.<Long>emptyList() : departmentIds) {
            if (id != null && id > 0) acl.add(new AgentKnowledgeLibraryService.AclSubject("DEPARTMENT", id));
        }
        Map<String, Object> library = libraryService.createLocalUpload(getTenantId(), getLoginUserId(), name,
                file == null ? null : file.getOriginalFilename(), file == null ? null : file.getContentType(),
                file == null ? null : file.getBytes(), accessMode, acl);
        Map<String, Object> result = new LinkedHashMap<>(library);
        result.put("sync", syncResult(number(library.get("libraryId"))));
        return result;
    }

    @PostMapping("/{libraryId}/sync")
    @Operation(summary = "立即同步知识源")
    public Map<String, Object> sync(@PathVariable("libraryId") long libraryId) {
        return syncResult(positive(libraryId));
    }

    @DeleteMapping("/{libraryId}")
    @Operation(summary = "停用知识源并使索引失效")
    public Map<String, Object> disable(@PathVariable("libraryId") long libraryId) {
        long id = positive(libraryId);
        libraryService.disable(getTenantId(), id);
        knowledgeService.invalidateManagedLibrary(getTenantId(), id);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("libraryId", id); result.put("status", "DISABLED");
        return result;
    }

    @GetMapping("/subjects")
    @Operation(summary = "搜索本地上传 ACL 可选部门或人员")
    public List<Map<String, Object>> subjects(@RequestParam("kind") String kind,
                                               @RequestParam(value = "keyword", required = false) String keyword) {
        String normalized = text(kind).toLowerCase(Locale.ROOT);
        return "departments".equals(normalized) ? departments(keyword) : users(keyword);
    }

    private Map<String, Object> syncResult(long libraryId) {
        try {
            return knowledgeService.syncManagedLibrary(getTenantId(), getLoginUserId(), libraryId);
        } catch (RuntimeException ex) {
            Map<String, Object> failed = new LinkedHashMap<>();
            failed.put("libraryId", libraryId); failed.put("status", "FAILED");
            failed.put("errorCode", ex.getClass().getSimpleName());
            return failed;
        }
    }

    private List<Map<String, Object>> users(String keyword) {
        String query = text(keyword).trim().toLowerCase(Locale.ROOT);
        List<Map<String, Object>> result = new ArrayList<>();
        for (AdminUserDO user : adminUserService.getUserListByStatus(CommonStatusEnum.ENABLE.getStatus())) {
            String nickname = text(user.getNickname());
            String username = text(user.getUsername());
            if (!query.isEmpty() && !nickname.toLowerCase(Locale.ROOT).contains(query)
                    && !username.toLowerCase(Locale.ROOT).contains(query)) continue;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", user.getId()); item.put("name", nickname); item.put("departmentId", user.getDeptId());
            result.add(item);
            if (result.size() >= 20) break;
        }
        return result;
    }

    private List<Map<String, Object>> departments(String keyword) {
        String pattern = "%" + text(keyword).trim().replace("%", "\\%").replace("_", "\\_") + "%";
        try {
            return jdbcTemplate.query("SELECT id, name, parent_id FROM system_dept WHERE tenant_id=? "
                            + "AND name ILIKE ? ESCAPE '\\' ORDER BY parent_id, id LIMIT 50",
                    (rs, rowNum) -> {
                        Map<String, Object> item = new LinkedHashMap<>();
                        item.put("id", rs.getLong("id")); item.put("name", rs.getString("name"));
                        item.put("parentId", rs.getObject("parent_id")); return item;
                    }, getTenantId(), pattern);
        } catch (RuntimeException ex) {
            // 部门候选仅用于管理表单，数据库部署未同步时返回空列表，不影响已有资料检索。
            return Collections.emptyList();
        }
    }

    private static long number(Object value) {
        if (value instanceof Number) return ((Number) value).longValue();
        try { return Long.parseLong(String.valueOf(value)); }
        catch (RuntimeException ex) { throw new IllegalArgumentException("编号必须为正整数"); }
    }
    private static long positive(long value) {
        if (value <= 0) throw new IllegalArgumentException("编号必须为正整数");
        return value;
    }
    private static Long positiveOrNull(Long value) { return value == null ? null : positive(value); }
    private static String text(Object value) { return value == null ? "" : String.valueOf(value); }
}
