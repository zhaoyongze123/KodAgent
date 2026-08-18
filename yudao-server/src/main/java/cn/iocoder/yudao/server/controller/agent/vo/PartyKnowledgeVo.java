package cn.iocoder.yudao.server.controller.agent.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.Max;
import javax.validation.constraints.Min;
import javax.validation.constraints.NotBlank;
import java.math.BigDecimal;
import java.util.List;

/** Public DTOs deliberately exclude source URL/path, attachment and audience data. */
public class PartyKnowledgeVo {

    private PartyKnowledgeVo() {
    }

    @Data
    public static class SearchRequest {
        @NotBlank
        @Schema(description = "关键词", requiredMode = Schema.RequiredMode.REQUIRED)
        private String query;

        @Min(1)
        @Max(20)
        @Schema(description = "最大返回条数", defaultValue = "5")
        private Integer topK = 5;

        @Schema(description = "文档类型")
        private String documentType;

        @Schema(description = "可选查询向量；仅在 pgvector 可用时参与召回")
        private List<BigDecimal> embedding;

        @Schema(description = "可选的 1536 维投影查询向量；优先用于索引召回")
        private List<BigDecimal> embeddingProjected;
    }

    @Data
    public static class Citation {
        private Long documentId;
        private Long chunkId;
        private String section;
        private Integer ordinal;
    }

    @Data
    public static class DocumentResponse {
        private Long id;
        private String title;
        private String type;
    }

    @Data
    public static class ChunkResponse {
        private Long id;
        private Long documentId;
        private String title;
        private String type;
        private String section;
        private Integer ordinal;
        private String content;
        private Citation citation;
    }

    @Data
    public static class SearchHit {
        private Long id;
        private String title;
        private String type;
        private String section;
        private Integer ordinal;
        private BigDecimal score;
        private String content;
        private Citation citation;
    }

    @Data
    public static class SearchResponse {
        private String query;
        private Integer total;
        @Schema(description = "实际检索模式：hybrid、keyword 或 keyword_degraded_*；降级不会绕过 OA 权限过滤")
        private String retrievalMode;
        private List<SearchHit> hits;
    }
}
