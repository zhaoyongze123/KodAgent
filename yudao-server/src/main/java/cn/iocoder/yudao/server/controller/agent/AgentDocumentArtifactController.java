package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentDocumentArtifactService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

/** 领域无关的 Agent 附件创建和受控下载入口。 */
@Tag(name = "Business Agent Artifacts")
@RestController
@RequestMapping("/agent/artifacts")
public class AgentDocumentArtifactController {
    @Resource private AgentDocumentArtifactService artifactService;

    @PostMapping
    @Operation(summary = "创建受控文档附件")
    public Map<String, Object> create(@RequestBody(required = false) Map<String, Object> request) {
        return artifactService.create(getTenantId(), getLoginUserId(), request);
    }

    @GetMapping("/{artifactId}/download")
    @Operation(summary = "下载当前用户有权访问的附件")
    public void download(@PathVariable("artifactId") String artifactId, HttpServletResponse response) throws Exception {
        if (artifactId == null || !artifactId.matches("[0-9a-fA-F-]{16,80}")) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "附件编号无效");
            return;
        }
        AgentDocumentArtifactService.ArtifactFile file;
        try {
            file = artifactService.download(getTenantId(), getLoginUserId(), artifactId);
        } catch (IllegalArgumentException ignored) {
            // 此接口面向浏览器下载代理，必须给出真实 HTTP 失败状态；若仍让全局
            // CommonResult 包成 200，代理会把错误 JSON 误当作 DOCX/XLSX 返回。
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "附件不存在、已过期或无权下载");
            return;
        }
        response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store, max-age=0");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.attachment()
                .filename(file.filename, StandardCharsets.UTF_8).build().toString());
        response.setHeader(HttpHeaders.CONTENT_TYPE, file.mimeType);
        response.setContentLengthLong(file.content.length);
        response.getOutputStream().write(file.content);
        response.getOutputStream().flush();
    }

    @GetMapping("/{artifactId}/preview")
    @Operation(summary = "预览当前用户有权访问的附件")
    public void preview(@PathVariable("artifactId") String artifactId, HttpServletResponse response) throws Exception {
        if (artifactId == null || !artifactId.matches("[0-9a-fA-F-]{16,80}")) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "附件编号无效");
            return;
        }
        AgentDocumentArtifactService.PreviewDocument preview;
        try {
            preview = artifactService.preview(getTenantId(), getLoginUserId(), artifactId);
        } catch (IllegalArgumentException ignored) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND, "附件不存在、已过期、无权访问或暂不支持预览");
            return;
        }
        response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store, max-age=0");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION, ContentDisposition.inline()
                .filename(preview.filename + ".html", StandardCharsets.UTF_8).build().toString());
        response.setContentType("text/html;charset=UTF-8");
        response.getOutputStream().write(preview.html.getBytes(StandardCharsets.UTF_8));
        response.getOutputStream().flush();
    }
}
