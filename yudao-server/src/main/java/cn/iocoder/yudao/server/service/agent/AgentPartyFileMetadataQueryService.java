package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.pojo.PageParam;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.time.Duration;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception0;

/**
 * Agent 党务文件元数据查询计划的确定性执行器。
 *
 * <p>职责是把 Python 已编译的只读计划转为 {@link PartyFileService} 的“当前用户可见”
 * 查询，再在这份已授权事实集合中完成允许字段的筛选、排序、截断和投影。它不读取正文、
 * 不执行写入，也不接受模型自定义字段或表达式，避免 Agent 计划越过通用党务服务边界。</p>
 */
@Service
public class AgentPartyFileMetadataQueryService {

    private static final Set<String> FILTER_FIELDS = new LinkedHashSet<>(
            Arrays.asList("title", "categoryId", "categoryName", "publishTime", "readStatus"));
    private static final Set<String> OPERATORS = new LinkedHashSet<>(
            Arrays.asList("EQ", "CONTAINS", "GTE", "LTE", "GT", "LT", "NOT_NULL"));
    private static final Set<String> RANK_FIELDS = new LinkedHashSet<>(
            Arrays.asList("publishTime", "title", "id"));
    private static final Set<String> PROJECTION_FIELDS = new LinkedHashSet<>(
            Arrays.asList("id", "title", "publishTime", "categoryName", "categoryId", "readStatus", "summary"));

    @Resource
    private PartyFileService partyFileService;

    /**
     * 执行经过编译的只读计划。
     *
     * @param userId 当前登录用户；可见性事实源，不能由请求体替代
     * @param rawPlan Python 编译器产生的结构化计划
     * @return 仅包含允许元数据字段的匹配列表及执行摘要
     */
    public Map<String, Object> execute(Long userId, Map<String, Object> rawPlan) {
        if (userId == null) {
            throw exception0(401, "缺少当前登录用户");
        }
        Map<String, Object> plan = rawPlan == null ? Collections.emptyMap() : rawPlan;
        if (!"party_file".equals(plan.get("entity")) || !"metadata_query".equals(plan.get("operation"))) {
            throw exception0(400, "党务文件元数据查询计划格式无效");
        }

        List<Map<String, Object>> filters = filters(plan.get("filters"));
        Rank rank = rank(plan.get("rank"));
        int limit = limit(plan.get("limit"));
        List<String> projection = projection(plan.get("projection"));

        // 查询服务先按当前用户的 ALL/USER/DEPT/ROLE 可见性生成事实集合；后续所有
        // in-memory 操作都只能缩小该集合，不能扩大权限范围。
        PartyFileMyPageReqVO request = new PartyFileMyPageReqVO();
        request.setPageNo(1).setPageSize(PageParam.PAGE_SIZE_NONE);
        PageResult<PartyFileRespVO> page = partyFileService.getMyPartyFilePage(userId, request);
        List<PartyFileRespVO> visible = page == null || page.getList() == null
                ? new ArrayList<>() : new ArrayList<>(page.getList());
        visible.removeIf(file -> !matchesAll(file, filters));
        visible.sort(comparator(rank));

        List<Map<String, Object>> matches = new ArrayList<>();
        for (PartyFileRespVO file : visible.subList(0, Math.min(limit, visible.size()))) {
            matches.add(project(file, projection));
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", matches.isEmpty() ? "NO_MATCH" : "READY");
        result.put("matches", matches);
        result.put("total", visible.size());
        result.put("limit", limit);
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> filters(Object value) {
        if (value == null) return Collections.emptyList();
        if (!(value instanceof List)) throw invalid("filters 必须是数组");
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : (List<?>) value) {
            if (!(item instanceof Map)) throw invalid("文件筛选条件格式无效");
            Map<String, Object> filter = (Map<String, Object>) item;
            String field = text(filter.get("field"));
            String operator = text(filter.get("operator")).toUpperCase(Locale.ROOT);
            if (!FILTER_FIELDS.contains(field) || !OPERATORS.contains(operator)) {
                throw invalid("党务文件查询包含未支持的筛选字段或操作符");
            }
            if (!"NOT_NULL".equals(operator) && filter.get("value") == null) {
                throw invalid("党务文件筛选条件缺少比较值");
            }
            Map<String, Object> normalized = new LinkedHashMap<>();
            normalized.put("field", field);
            normalized.put("operator", operator);
            normalized.put("value", filter.get("value"));
            result.add(normalized);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private Rank rank(Object value) {
        if (value == null) return new Rank("publishTime", "desc", null);
        if (!(value instanceof Map)) throw invalid("rank 必须是对象");
        Map<String, Object> raw = (Map<String, Object>) value;
        String field = text(raw.get("field"));
        String mode = text(raw.get("mode")).toLowerCase(Locale.ROOT);
        if (!RANK_FIELDS.contains(field) || !("asc".equals(mode) || "desc".equals(mode) || "nearest".equals(mode))) {
            throw invalid("党务文件排序字段或方式不受支持");
        }
        if ("nearest".equals(mode)) {
            // 编译器只允许发布时间做最近时间排序。目标时间必须由编译期规范化，
            // Java 再次解析，不能把任意字符串交给排序逻辑猜测。
            if (!"publishTime".equals(field) || raw.get("target") == null) {
                throw invalid("党务文件最近时间排序必须提供 publishTime 和 target");
            }
            return new Rank(field, mode, parseDateTime(raw.get("target")));
        }
        return new Rank(field, mode, null);
    }

    private int limit(Object value) {
        if (value == null) return 20;
        try {
            int parsed = Integer.parseInt(String.valueOf(value));
            if (parsed >= 1 && parsed <= 50) return parsed;
        } catch (NumberFormatException ignored) {
            // 统一按计划非法返回，不把异常细节暴露为业务信息。
        }
        throw invalid("limit 必须是 1 到 50 之间的整数");
    }

    @SuppressWarnings("unchecked")
    private List<String> projection(Object value) {
        if (value == null) return Arrays.asList("id", "title", "publishTime", "categoryName");
        if (!(value instanceof List)) throw invalid("projection 必须是数组");
        List<String> result = new ArrayList<>();
        for (Object field : (List<?>) value) {
            String name = text(field);
            if (!PROJECTION_FIELDS.contains(name)) throw invalid("党务文件投影包含未支持字段");
            if (!result.contains(name)) result.add(name);
        }
        return result.isEmpty() ? Arrays.asList("id", "title", "publishTime", "categoryName") : result;
    }

    private boolean matchesAll(PartyFileRespVO file, List<Map<String, Object>> filters) {
        for (Map<String, Object> filter : filters) {
            Object actual = field(file, String.valueOf(filter.get("field")));
            String operator = String.valueOf(filter.get("operator"));
            Object expected = filter.get("value");
            if (!matches(actual, operator, expected)) return false;
        }
        return true;
    }

    private boolean matches(Object actual, String operator, Object expected) {
        if ("NOT_NULL".equals(operator)) return actual != null;
        if (actual == null) return false;
        if ("CONTAINS".equals(operator)) {
            return String.valueOf(actual).toLowerCase(Locale.ROOT)
                    .contains(String.valueOf(expected).toLowerCase(Locale.ROOT));
        }
        int comparison = compare(actual, expected);
        switch (operator) {
            case "EQ": return comparison == 0;
            case "GTE": return comparison >= 0;
            case "LTE": return comparison <= 0;
            case "GT": return comparison > 0;
            case "LT": return comparison < 0;
            default: return false;
        }
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private int compare(Object actual, Object expected) {
        if (actual instanceof LocalDateTime) {
            return ((LocalDateTime) actual).compareTo(parseDateTime(expected));
        }
        if (actual instanceof Number) {
            return java.math.BigDecimal.valueOf(((Number) actual).doubleValue())
                    .compareTo(new java.math.BigDecimal(String.valueOf(expected)));
        }
        if (actual instanceof Boolean) {
            return Boolean.valueOf(String.valueOf(actual)).compareTo(Boolean.valueOf(String.valueOf(expected)));
        }
        if (actual instanceof Comparable) return ((Comparable) actual).compareTo(String.valueOf(expected));
        return String.valueOf(actual).compareTo(String.valueOf(expected));
    }

    private Comparator<PartyFileRespVO> comparator(Rank rank) {
        if ("nearest".equals(rank.mode)) {
            return Comparator.<PartyFileRespVO>comparingLong(file -> distanceToTarget(file.getPublishTime(), rank.target))
                    .thenComparing(file -> file.getId() == null ? Long.MAX_VALUE : file.getId());
        }
        Comparator<PartyFileRespVO> comparator = (left, right) -> compareNullable(
                field(left, rank.field), field(right, rank.field));
        if ("desc".equals(rank.mode)) comparator = comparator.reversed();
        return comparator.thenComparing(file -> file.getId() == null ? Long.MAX_VALUE : file.getId());
    }

    /** 计算发布时间与指定目标的绝对秒差；空发布时间始终排在最后。 */
    private long distanceToTarget(LocalDateTime publishTime, LocalDateTime target) {
        if (publishTime == null || target == null) return Long.MAX_VALUE;
        try {
            return Math.abs(Duration.between(publishTime, target).getSeconds());
        } catch (ArithmeticException ignored) {
            return Long.MAX_VALUE;
        }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private int compareNullable(Object left, Object right) {
        if (left == right) return 0;
        if (left == null) return 1;
        if (right == null) return -1;
        return ((Comparable) left).compareTo(right);
    }

    private Object field(PartyFileRespVO file, String name) {
        switch (name) {
            case "id": return file.getId();
            case "title": return file.getTitle();
            case "categoryId": return file.getCategoryId();
            case "categoryName": return file.getCategoryName();
            case "publishTime": return file.getPublishTime();
            case "readStatus": return file.getReadStatus();
            case "summary": return file.getSummary();
            default: return null;
        }
    }

    private Map<String, Object> project(PartyFileRespVO file, List<String> projection) {
        Map<String, Object> item = new LinkedHashMap<>();
        for (String field : projection) item.put(field, field(file, field));
        return item;
    }

    private LocalDateTime parseDateTime(Object value) {
        String text = String.valueOf(value).trim();
        for (DateTimeFormatter formatter : Arrays.asList(
                DateTimeFormatter.ISO_LOCAL_DATE_TIME,
                DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))) {
            try { return LocalDateTime.parse(text, formatter); }
            catch (DateTimeParseException ignored) { }
        }
        throw invalid("党务文件时间筛选值格式无效");
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private RuntimeException invalid(String message) {
        return exception0(400, message);
    }

    /** 已校验的排序字段和方向。 */
    private static final class Rank {
        private final String field;
        private final String mode;

        private final LocalDateTime target;

        private Rank(String field, String mode, LocalDateTime target) {
            this.field = field;
            this.mode = mode;
            this.target = target;
        }
    }
}
