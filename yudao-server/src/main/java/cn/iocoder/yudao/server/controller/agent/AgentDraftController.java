package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.service.agent.AgentDraftService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

@Tag(name = "Business Agent Drafts")
@RestController
@RequestMapping("/agent/drafts")
public class AgentDraftController {

    @Resource
    private AgentDraftService agentDraftService;

    @PostMapping("/meeting-booking")
    @Operation(summary = "保存会议预约草稿")
    public Map<String, Object> saveMeetingBookingDraft(@RequestBody Map<String, Object> request) {
        return agentDraftService.saveMeetingBookingDraft(getTenantId(), getLoginUserId(), request);
    }

    @GetMapping("/meeting-booking/{draftId}")
    @Operation(summary = "读取会议预约草稿")
    public Map<String, Object> getMeetingBookingDraft(@PathVariable String draftId) {
        return agentDraftService.getMeetingBookingDraft(getTenantId(), getLoginUserId(), draftId);
    }

    @DeleteMapping("/meeting-booking/{draftId}")
    @Operation(summary = "删除会议预约草稿")
    public void deleteMeetingBookingDraft(@PathVariable String draftId) {
        agentDraftService.deleteMeetingBookingDraft(getTenantId(), getLoginUserId(), draftId);
    }

    @PostMapping("/meeting-booking/{draftId}/status")
    @Operation(summary = "更新会议预约草稿状态")
    public void updateMeetingBookingDraftStatus(@PathVariable String draftId,
                                                 @RequestBody Map<String, Object> request) {
        agentDraftService.updateMeetingBookingDraftStatus(
                getTenantId(), getLoginUserId(), draftId, String.valueOf(request.get("status")));
    }
}
