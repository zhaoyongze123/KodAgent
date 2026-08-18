package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category.PartyFileCategoryRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileAttachmentRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileReadSourceEnum;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileAttachmentService;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileCategoryService;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import cn.iocoder.yudao.server.service.agent.AgentPartyFileDraftService;
import cn.iocoder.yudao.server.service.agent.AgentPartyFileMetadataQueryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import javax.validation.Valid;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.LinkedHashMap;
import java.util.Collections;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserNickname;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_ATTACHMENT_NOT_FOUND;

@Tag(name = "Business Agent Party File Tools")
@RestController
@RequestMapping("/agent/tools")
public class AgentPartyFileToolController {
    @Resource private PartyFileService partyFileService;
    @Resource private PartyFileCategoryService partyFileCategoryService;
    @Resource private PartyFileAttachmentService partyFileAttachmentService;
    @Resource private AgentPartyFileDraftService partyFileDraftService;
    @Resource private AgentPartyFileMetadataQueryService partyFileMetadataQueryService;

    @GetMapping("/party-files/my-page") @Operation(summary = "获取当前用户可见的党务文件")
    public PageResult<PartyFileRespVO> listMyPartyFiles(@Valid PartyFileMyPageReqVO request) { return partyFileService.getMyPartyFilePage(getLoginUserId(), request); }

    @PostMapping("/party-files/query-plan") @Operation(summary = "执行当前用户可见党务文件元数据查询计划")
    public Map<String, Object> queryPartyFileMetadataPlan(@RequestBody Map<String, Object> plan) {
        return partyFileMetadataQueryService.execute(getLoginUserId(), plan);
    }

    @GetMapping("/party-files/my-get") @Operation(summary = "获取党务文件详情并记录已读")
    public PartyFileRespVO getMyPartyFile(@RequestParam("id") Long id) { return partyFileService.getMyPartyFileDetail(id, getLoginUserId(), getLoginUserNickname()); }

    @GetMapping("/party-files/my-attachment") @Operation(summary = "获取党务文件附件信息")
    public PartyFileRespVO getMyPartyFileAttachment(@RequestParam("id") Long id, @RequestParam("fileId") Long fileId, @RequestParam(value = "action", required = false) String action) {
        return partyFileService.getMyPartyFileAttachment(id, fileId, getLoginUserId(), getLoginUserNickname(), PartyFileReadSourceEnum.fromAction(action).getSource());
    }

    /**
     * Same authenticated business boundary used by the Next.js attachment
     * proxy.  It deliberately validates both audience visibility and the
     * file's ownership before returning bytes, so a guessed fileId cannot be
     * used to read another party file's attachment.
     */
    @GetMapping("/party-files/my-attachment/content")
    @Operation(summary = "预览或下载当前用户可见的党务文件附件")
    public void streamMyPartyFileAttachment(@RequestParam("id") Long id,
                                            @RequestParam("fileId") Long fileId,
                                            @RequestParam(value = "action", defaultValue = "preview") String action,
                                            HttpServletResponse response) throws Exception {
        boolean preview = "preview".equalsIgnoreCase(action);
        boolean download = "download".equalsIgnoreCase(action);
        if (!preview && !download) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST, "action must be preview or download");
            return;
        }
        try {
            PartyFileRespVO detail = partyFileService.getMyPartyFileAttachment(id, fileId,
                    getLoginUserId(), getLoginUserNickname(),
                    (preview ? PartyFileReadSourceEnum.PREVIEW : PartyFileReadSourceEnum.DOWNLOAD).getSource());
            PartyFileAttachmentRespVO attachment = detail.getAttachments().stream()
                    .filter(item -> Objects.equals(item.getId(), fileId))
                    .findFirst()
                    .orElseThrow(() -> exception(PARTY_FILE_ATTACHMENT_NOT_FOUND));
            byte[] content = partyFileAttachmentService.getAttachmentContent(fileId);
            if (!preview) {
                ServletUtils.writeAttachment(response, attachment.getName(), content);
                return;
            }
            response.setHeader("Content-Disposition", "inline;filename=" + HttpUtils.encodeUtf8(attachment.getName()));
            response.setContentType(attachment.getType() != null ? attachment.getType() : "application/octet-stream");
            response.getOutputStream().write(content);
            response.getOutputStream().flush();
        } catch (ServiceException ex) {
            // The global exception handler intentionally keeps JSON business
            // errors compatible with the OA API (HTTP 200). A byte endpoint
            // must not do that: browsers and the Next proxy would otherwise
            // treat an error object as a successful attachment. Return an
            // explicit upstream failure status while keeping the detail in
            // server logs and exposing only a stable client-facing contract.
            response.resetBuffer();
            response.setStatus(HttpServletResponse.SC_BAD_GATEWAY);
            response.setContentType("application/json;charset=UTF-8");
            ServletUtils.writeJSON(response, CommonResult.error(HttpServletResponse.SC_BAD_GATEWAY,
                    "党务文件附件暂不可用，请检查可道云来源配置"));
        }
    }

    @GetMapping("/party-files/categories") @Operation(summary = "获取启用的党务文件分类")
    public List<PartyFileCategoryRespVO> listPartyFileCategories() {
        return cn.iocoder.yudao.framework.common.util.object.BeanUtils.toBean(partyFileCategoryService.getCategoryList(CommonStatusEnum.ENABLE.getStatus()), PartyFileCategoryRespVO.class);
    }

    @GetMapping("/party-files/manage/{partyFileId}")
    @Operation(summary = "读取可编辑党务文件详情")
    public Map<String, Object> getManageDetail(@PathVariable Long partyFileId) {
        return partyFileDraftService.detail(partyFileId, getLoginUserId());
    }

    @PostMapping("/party-files/drafts/{operation}")
    @Operation(summary = "按授权操作创建党务文件草稿")
    public Map<String, Object> saveDraftByOperation(@PathVariable String operation,
                                                    @RequestBody Map<String, Object> request) {
        String normalized = operation == null ? "" : operation.trim().toUpperCase();
        if (!java.util.Arrays.asList("CREATE", "UPDATE", "DELETE").contains(normalized)) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(400, "党务文件草稿操作无效");
        }
        Map<String, Object> copy = new LinkedHashMap<>(request == null ? Collections.emptyMap() : request);
        Object requested = copy.put("operation", normalized);
        if (requested != null && !normalized.equalsIgnoreCase(String.valueOf(requested))) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(409, "PARTY_FILE_OPERATION_MISMATCH：路径与草稿操作不一致");
        }
        return partyFileDraftService.save(getTenantId(), getLoginUserId(), copy);
    }

    @GetMapping("/party-files/drafts/{draftId}")
    @Operation(summary = "读取当前用户党务文件草稿")
    public Map<String, Object> getDraft(@PathVariable String draftId) {
        return partyFileDraftService.getDraft(getTenantId(), getLoginUserId(), draftId);
    }

    @PostMapping("/party-files/commit/{operation}")
    @Operation(summary = "按已授权操作确认并提交党务文件草稿")
    public Map<String, Object> commitDraftByOperation(@PathVariable String operation, @RequestBody Map<String, Object> request) {
        Object draftId = request.get("draftId"), approvalId = request.get("approvalId"), operationId = request.get("operationId");
        if (draftId == null || approvalId == null || operationId == null) throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(400, "draftId、approvalId 和 operationId 不能为空");
        return partyFileDraftService.commit(getTenantId(), getLoginUserId(), String.valueOf(draftId), String.valueOf(approvalId), operation, String.valueOf(operationId));
    }

    @GetMapping("/party-files/commit/status")
    @Operation(summary = "查询党务文件提交结果，用于恢复丢失响应")
    public Map<String, Object> getPartyFileCommitStatus(
            @RequestParam String draftId,
            @RequestParam String approvalId,
            @RequestParam String operationId) {
        Map<String, Object> result = partyFileDraftService.findCommitStatus(
                getTenantId(), getLoginUserId(), draftId, approvalId, operationId);
        if (result == null) {
            throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(
                    404, "党务文件提交结果尚未落库");
        }
        return result;
    }

    @GetMapping("/party-files/report")
    @Operation(summary = "汇总当前用户可见党务文件")
    public Map<String, Object> partyFileReport(
            @RequestParam @org.springframework.format.annotation.DateTimeFormat(pattern = cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime startTime,
            @RequestParam @org.springframework.format.annotation.DateTimeFormat(pattern = cn.iocoder.yudao.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND) java.time.LocalDateTime endTime) {
        if (!endTime.isAfter(startTime)) throw cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0(400, "报表结束时间必须晚于开始时间");
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("entity", "party_file"); plan.put("operation", "metadata_query"); plan.put("limit", 50);
        plan.put("filters", java.util.Arrays.asList(
                new LinkedHashMap<String, Object>() {{ put("field", "publishTime"); put("operator", "GTE"); put("value", startTime.toString()); }},
                new LinkedHashMap<String, Object>() {{ put("field", "publishTime"); put("operator", "LT"); put("value", endTime.toString()); }}));
        plan.put("rank", new LinkedHashMap<String, Object>() {{ put("field", "publishTime"); put("mode", "desc"); }});
        Map<String, Object> raw = partyFileMetadataQueryService.execute(getLoginUserId(), plan);
        List<?> matches = raw.get("matches") instanceof List ? (List<?>) raw.get("matches") : Collections.emptyList();
        int read = 0;
        Map<String, Integer> byCategory = new LinkedHashMap<>();
        for (Object value : matches) if (value instanceof Map) {
            Map<?, ?> item = (Map<?, ?>) value;
            if (Boolean.TRUE.equals(item.get("readStatus"))) read++;
            Object categoryValue = item.containsKey("categoryName") ? item.get("categoryName") : "未分类";
            String category = String.valueOf(categoryValue);
            byCategory.merge(category, 1, Integer::sum);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportType", "party_file"); result.put("startTime", startTime); result.put("endTime", endTime);
        result.put("total", matches.size()); result.put("readCount", read); result.put("unreadCount", matches.size() - read);
        result.put("byCategory", byCategory); result.put("items", matches);
        return result;
    }
}
