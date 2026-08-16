package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.server.service.agent.AgentProjectAnalysisService;
import cn.iocoder.yudao.server.service.agent.AgentProjectAuditService;
import cn.iocoder.yudao.server.service.agent.AgentProjectReportService;
import cn.iocoder.yudao.server.service.agent.AgentProjectKnowledgeService;
import cn.iocoder.yudao.server.service.agent.KodProjectBridgeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/**
 * 项目插件 Agent 工具的受控 HTTP 入口。
 *
 * <p>本文件只负责 HTTP 参数、当前登录身份和字节下载适配。项目可见性、任务隐私、
 * 文件权限均由 KodProjectBridgeService 转至 KodCloud project 插件实时复核；统计
 * 由 AgentProjectAnalysisService 确定性计算，模型永远不能直接访问本控制器以外的
 * KodCloud 数据或数据库。</p>
 */
@Tag(name = "Business Agent Project Tools")
@RestController
@RequestMapping("/agent/tools/projects")
public class AgentProjectToolController {

    @Resource
    private KodProjectBridgeService bridgeService;
    @Resource
    private AgentProjectAnalysisService analysisService;
    @Resource
    private AgentProjectReportService reportService;
    @Resource
    private AgentProjectKnowledgeService knowledgeService;
    @Resource
    private AgentProjectAuditService auditService;

    /** 分页返回当前用户在 KodCloud 项目插件内可见的项目。 */
    @GetMapping
    @Operation(summary = "获取当前用户可参与的项目")
    public Map<String, Object> listProjects(
            @RequestParam(value = "page", required = false) Integer page,
            @RequestParam(value = "pageNo", required = false) Integer pageNo,
            @RequestParam(value = "pageSize", defaultValue = "20") int pageSize) {
        Map<String, Object> raw = bridgeService.listProjects(getTenantId(), getLoginUserId());
        List<Map<String, Object>> items = maps(raw.get("items"));
        int normalizedPage = Math.max(1, page != null ? page : pageNo == null ? 1 : pageNo);
        int normalizedSize = Math.min(100, Math.max(1, pageSize));
        int start = Math.min(items.size(), (normalizedPage - 1) * normalizedSize);
        int end = Math.min(items.size(), start + normalizedSize);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("items", new ArrayList<>(items.subList(start, end)));
        result.put("total", items.size());
        result.put("page", normalizedPage);
        result.put("pageSize", normalizedSize);
        result.put("asOf", raw.get("asOf"));
        return result;
    }

    /** 读取项目快照，包含当前用户可见的配置、成员、任务汇总和资料状态。 */
    @GetMapping("/{projectId}/snapshot")
    @Operation(summary = "读取项目事实快照")
    public Map<String, Object> snapshot(@PathVariable("projectId") long projectId) {
        return bridgeService.snapshot(getTenantId(), getLoginUserId(), positive(projectId));
    }

    /** 读取当前用户可见的项目任务树；taskShowOnlySelf 由插件端执行。 */
    @GetMapping("/{projectId}/tasks")
    @Operation(summary = "读取当前用户可见的项目任务")
    public Map<String, Object> tasks(@PathVariable("projectId") long projectId) {
        return bridgeService.tasks(getTenantId(), getLoginUserId(), positive(projectId));
    }

    /** 读取项目和当前可见任务的日志活动。 */
    @GetMapping("/{projectId}/activity")
    @Operation(summary = "读取项目任务活动")
    public Map<String, Object> activity(@PathVariable("projectId") long projectId,
                                         @RequestParam(value = "fromTime", required = false) Long fromTime) {
        Map<String, Object> raw = bridgeService.activity(getTenantId(), getLoginUserId(), positive(projectId));
        if (fromTime == null || fromTime <= 0) return raw;
        List<Map<String, Object>> filtered = new ArrayList<>();
        for (Map<String, Object> item : maps(raw.get("items"))) {
            if (epoch(item.get("createdAt")) >= fromTime) filtered.add(item);
        }
        Map<String, Object> result = new LinkedHashMap<>(raw);
        result.put("items", filtered);
        result.put("fromTime", fromTime);
        return result;
    }

    /** 返回项目资料的脱敏元数据，不暴露文件路径、分享链接或访问令牌。 */
    @GetMapping("/{projectId}/documents")
    @Operation(summary = "读取项目资料目录")
    public Map<String, Object> documents(@PathVariable("projectId") long projectId) {
        return bridgeService.documents(getTenantId(), getLoginUserId(), positive(projectId));
    }

    /** 管理员或项目成员手动触发一次项目资料增量同步；同步结果只返回数量和状态。 */
    @PostMapping("/{projectId}/documents/sync")
    @Operation(summary = "立即同步项目资料")
    public Map<String, Object> syncDocuments(@PathVariable("projectId") long projectId) {
        return knowledgeService.syncProject(getTenantId(), getLoginUserId(), positive(projectId), "MANUAL");
    }

    /** 在当前项目权限范围内检索资料，并按开关决定是否合并共享制度库。 */
    @PostMapping("/{projectId}/knowledge/search")
    @Operation(summary = "检索项目资料与制度知识")
    public Map<String, Object> searchKnowledge(@PathVariable("projectId") long projectId,
                                                @RequestBody Map<String, Object> request) {
        String query = String.valueOf(request == null ? "" : request.getOrDefault("query", ""));
        int topK = integer(request == null ? null : request.get("topK"), 5);
        boolean includePolicy = !Boolean.FALSE.equals(request == null ? null : request.get("includePolicyLibrary"));
        return knowledgeService.search(getTenantId(), getLoginUserId(), positive(projectId), query, topK, includePolicy);
    }

    /** 从同一快照计算项目卡片需要的确定性统计结果。 */
    @GetMapping("/{projectId}/analysis")
    @Operation(summary = "计算项目进度与风险分析")
    public Map<String, Object> analysis(@PathVariable("projectId") long projectId) {
        Map<String, Object> snapshot = bridgeService.snapshot(getTenantId(), getLoginUserId(), positive(projectId));
        Map<String, Object> result = analysisService.analyze(snapshot);
        auditService.record(getTenantId(), getLoginUserId(), positive(projectId), "ANALYZE",
                epoch(map(result.get("kpis")).get("asOf")), Collections.emptyList(), null, null);
        return result;
    }

    /**
     * 仅兼容历史项目报告的下载。新附件一律通过 /agent/artifacts 创建与下载，
     * 不再新增项目专用报告卡或固定模板文件。
     */
    @GetMapping("/reports/{reportId}/download")
    @Operation(summary = "下载当前用户的项目报告")
    public void download(@PathVariable("reportId") String reportId,
                         @RequestParam(value = "format", defaultValue = "docx") String format,
                         HttpServletResponse response) throws Exception {
        AgentProjectReportService.ReportFile report = reportService.download(
                getTenantId(), getLoginUserId(), reportId, format);
        String contentType = "docx".equalsIgnoreCase(format)
                ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
        response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store, max-age=0");
        // RFC 5987 filename* 明确声明 UTF-8，不能把中文文件名按 ISO-8859-1 重解释；
        // 后者会导致下载名乱码，并且不同浏览器的补偿行为不一致。
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment()
                .filename(report.filename, java.nio.charset.StandardCharsets.UTF_8)
                .build().toString());
        response.setContentType(contentType);
        response.setContentLengthLong(report.content.length);
        response.getOutputStream().write(report.content);
        response.getOutputStream().flush();
    }

    /**
     * 管理员建立 OA 与 KodCloud 用户绑定。实际授权由 X-Agent-Permission=project:manage
     * 进入认证拦截器后校验；此处不允许调用方指定租户或操作者。
     */
    @PostMapping("/bindings")
    @Operation(summary = "管理员绑定 OA 与 KodCloud 用户")
    public Map<String, Object> bindUser(@RequestBody Map<String, Object> request) {
        long oaUserId = number(request.get("oaUserId"));
        long kodUserId = number(request.get("kodUserId"));
        bridgeService.bindUser(getTenantId(), positive(oaUserId), positive(kodUserId), getLoginUserId());
        return Map.of("status", "ACTIVE", "oaUserId", oaUserId, "kodUserId", kodUserId);
    }

    /**
     * 管理员绑定共享制度目录和独立只读服务账号，并立即执行一次首次同步。
     * 请求只接受 KodCloud 编号，不接受路径、下载链接或 accessToken。
     */
    @PostMapping("/policy-library/binding")
    @Operation(summary = "管理员绑定共享制度目录")
    public Map<String, Object> bindPolicyLibrary(@RequestBody Map<String, Object> request) {
        long folderId = number(request.get("folderId"));
        long serviceKodUserId = number(request.get("serviceKodUserId"));
        bridgeService.bindPolicyLibrary(getTenantId(), positive(folderId), positive(serviceKodUserId), getLoginUserId());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "ACTIVE");
        result.put("folderId", folderId);
        result.put("serviceKodUserId", serviceKodUserId);
        result.put("sync", knowledgeService.syncPolicyLibrary(getTenantId(), getLoginUserId()));
        return result;
    }

    /** 管理员手动刷新制度库索引，返回数量和状态，不返回文件正文。 */
    @PostMapping("/policy-library/sync")
    @Operation(summary = "立即同步共享制度库")
    public Map<String, Object> syncPolicyLibrary() {
        return knowledgeService.syncPolicyLibrary(getTenantId(), getLoginUserId());
    }

    /** 物理停用当前租户的制度库绑定，并立即使旧检索副本失效。 */
    @org.springframework.web.bind.annotation.DeleteMapping("/policy-library/binding")
    @Operation(summary = "停用共享制度库")
    public Map<String, Object> unbindPolicyLibrary() {
        bridgeService.unbindPolicyLibrary(getTenantId());
        return Map.of("status", "DISABLED");
    }

    private static long positive(long value) {
        if (value <= 0) throw new IllegalArgumentException("项目或用户编号必须为正整数");
        return value;
    }

    private static long number(Object value) {
        if (value instanceof Number) return ((Number) value).longValue();
        try { return Long.parseLong(String.valueOf(value)); }
        catch (RuntimeException ex) { throw new IllegalArgumentException("项目或用户编号必须为正整数"); }
    }

    private static int integer(Object value, int fallback) {
        if (value == null) return fallback;
        try { return Math.min(20, Math.max(1, Integer.parseInt(String.valueOf(value)))); }
        catch (RuntimeException ex) { return fallback; }
    }

    private static long epoch(Object value) {
        if (value instanceof Number) {
            long result = ((Number) value).longValue();
            return result > 10_000_000_000L ? result / 1000L : result;
        }
        try { return Long.parseLong(String.valueOf(value)); }
        catch (RuntimeException ex) { return 0L; }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> maps(Object value) {
        if (!(value instanceof List)) return Collections.emptyList();
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : (List<?>) value) if (item instanceof Map) result.add((Map<String, Object>) item);
        return result;
    }
}
