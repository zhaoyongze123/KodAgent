package cn.iocoder.yudao.server.controller.agent;

import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.ChunkResponse;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.DocumentResponse;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.SearchRequest;
import cn.iocoder.yudao.server.controller.agent.vo.PartyKnowledgeVo.SearchResponse;
import cn.iocoder.yudao.server.service.agent.PartyKnowledgeFacadeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.validation.Valid;
import java.util.Map;

import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId;
import static cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserNickname;
import static cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getTenantId;

@Tag(name = "Business Agent Party Knowledge Tools")
@RestController
@RequestMapping("/agent/tools/party-knowledge")
@Validated
public class AgentPartyKnowledgeToolController {

    @Resource
    private PartyKnowledgeFacadeService partyKnowledgeFacadeService;

    @GetMapping("/search")
    @Operation(summary = "检索当前用户可见的党务知识")
    public SearchResponse search(@Valid SearchRequest request) {
        return partyKnowledgeFacadeService.search(getTenantId(), getLoginUserId(), getLoginUserNickname(), request);
    }

    @PostMapping("/search")
    @Operation(summary = "检索当前用户可见的党务知识（支持结构化查询向量）")
    public SearchResponse searchPost(@Valid @RequestBody SearchRequest request) {
        return partyKnowledgeFacadeService.search(getTenantId(), getLoginUserId(), getLoginUserNickname(), request);
    }

    @GetMapping("/health")
    @Operation(summary = "读取党务知识索引和向量检索健康状态")
    public Map<String, Object> health() {
        return partyKnowledgeFacadeService.health(getTenantId(), getLoginUserId());
    }

    @GetMapping("/documents/{documentId}")
    @Operation(summary = "读取当前用户可见的知识文档摘要")
    public DocumentResponse getDocument(@PathVariable Long documentId) {
        return partyKnowledgeFacadeService.getDocument(getTenantId(), getLoginUserId(), getLoginUserNickname(), documentId);
    }

    @GetMapping("/chunks/{chunkId}")
    @Operation(summary = "读取当前用户可见的知识切片")
    public ChunkResponse getChunk(@PathVariable Long chunkId) {
        return partyKnowledgeFacadeService.getChunk(getTenantId(), getLoginUserId(), getLoginUserNickname(), chunkId);
    }
}
