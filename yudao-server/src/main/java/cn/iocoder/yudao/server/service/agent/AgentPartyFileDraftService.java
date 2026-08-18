package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileCategoryDO;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileCategoryService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.Resource;
import java.lang.reflect.Array;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.*;

/** Durable confirmation boundary for party-file create/update/delete. */
@Service
public class AgentPartyFileDraftService {
    private static final Logger log = LoggerFactory.getLogger(AgentPartyFileDraftService.class);
    @Resource @Qualifier("agentEventJdbcTemplate") private JdbcTemplate jdbcTemplate;
    @Resource private PartyFileService partyFileService;
    @Resource private PartyFileCategoryService partyFileCategoryService;
    @Resource private AgentApprovalService agentApprovalService;
    @Resource private AgentPartyFileBusinessCommitService businessCommitService;
    @Resource private PermissionService permissionService;

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> save(Long tenantId, Long userId, Map<String, Object> request) {
        String operation = required(request, "operation").toUpperCase(Locale.ROOT);
        if (!Arrays.asList("CREATE", "UPDATE", "DELETE").contains(operation)) throw bad("党务文件操作必须是 CREATE、UPDATE 或 DELETE");
        requirePermission(userId, operation);
        String key = required(request, "idempotencyKey"), run = required(request, "runId"), thread = required(request, "threadId"), message = required(request, "messageId");
        String operationId = required(request, "operationId");
        if (operationId.length() > 128) throw bad("党务文件草稿 operationId 无效");
        Map<String, Object> existing = findPending(tenantId, userId, key, run, thread, message, operationId);
        if (existing != null) return existing;
        Long sourceId = number(request.get("sourcePartyFileId"));
        PartyFileRespVO source = null;
        if (!"CREATE".equals(operation)) {
            if (sourceId == null) throw bad("修改或删除党务文件必须指定 sourcePartyFileId");
            source = partyFileService.getPartyFileDetail(sourceId);
            if (source == null) throw ServiceExceptionUtil.exception0(404, "党务文件不存在");
        }
        String draftId = UUID.randomUUID().toString();
        Map<String, Object> draft = new LinkedHashMap<>(request);
        // UPDATE is a field-level operation.  The caller may provide only the
        // changed title/content/etc.; fill the remaining required fields from
        // the Java-authorized source snapshot before validating and persisting
        // the draft.  This keeps the model from having to replay the entire
        // document and prevents a partial update from becoming an accidental
        // CREATE or an invalid empty payload.
        if ("UPDATE".equals(operation) && source != null) {
            mergeUpdateDefaults(draft, snapshot(source));
            if (nullable(draft.get("categoryName")) == null && nullable(source.getCategoryName()) != null) {
                draft.put("categoryName", source.getCategoryName());
            }
        }
        if (!"DELETE".equals(operation)) validatePayload(draft);
        decoratePresentation(draft, source);
        draft.put("draftId", draftId); draft.put("operation", operation); draft.put("sourcePartyFileId", sourceId);
        draft.put("operationId", operationId);
        if (source != null) draft.put("sourceSnapshot", snapshot(source));
        String approvalId = agentApprovalService.createGeneric(tenantId, userId, run, thread, message,
                null, draftId, "PARTY_FILE", draft, operationId);
        draft.put("approvalId", approvalId);
        jdbcTemplate.update("INSERT INTO agent_party_file_draft (draft_id, approval_id, tenant_id, owner_user_id, run_id, thread_id, message_id, operation_id, idempotency_key, operation, source_party_file_id, source_snapshot, status, draft_data, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), 'PENDING', CAST(? AS jsonb), CURRENT_TIMESTAMP + INTERVAL '24 hours')",
                draftId, approvalId, tenantId, userId, run, thread, message, operationId, key, operation, sourceId,
                JsonUtils.toJsonString(source == null ? Collections.emptyMap() : snapshot(source)), JsonUtils.toJsonString(draft));
        return result(draftId, approvalId, draft);
    }

    public Map<String, Object> getDraft(Long tenantId, Long userId, String draftId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT approval_id, status, draft_data::text, result_data::text "
                        + "FROM agent_party_file_draft WHERE draft_id = ? AND tenant_id = ? "
                        + "AND owner_user_id = ? AND status IN ('PENDING', 'SUBMITTING', 'SUBMITTED') "
                        + "AND archived_at IS NULL AND (status <> 'PENDING' OR expires_at > CURRENT_TIMESTAMP)",
                (rs, i) -> {
                    Map<String, Object> value = result(draftId, rs.getString("approval_id"),
                            JsonUtils.parseObject(rs.getString("draft_data"), Map.class));
                    value.put("status", rs.getString("status"));
                    String resultData = rs.getString("result_data");
                    if (resultData != null) value.put("result", JsonUtils.parseObject(resultData, Map.class));
                    return value;
                }, draftId, tenantId, userId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(404, "党务文件草稿不存在、已处理或已过期");
        return rows.get(0);
    }

    public Map<String, Object> detail(Long id, Long userId) {
        if (!permissionService.hasAnyPermissions(userId, "system:party-file:update", "system:party-file:delete")) {
            throw ServiceExceptionUtil.exception0(403, "无权读取党务文件编辑详情");
        }
        PartyFileRespVO file = partyFileService.getPartyFileDetail(id);
        if (file == null) throw ServiceExceptionUtil.exception0(404, "党务文件不存在");
        return snapshot(file);
    }

    /** Read-only recovery projection for an Effect in UNKNOWN state. */
    public Map<String, Object> findCommitStatus(Long tenantId, Long userId, String draftId,
                                                String approvalId, String operationId) {
        String validOperationId = required(operationId, "operationId");
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, idempotency_key, operation_id, result_data::text "
                        + "FROM agent_party_file_draft WHERE draft_id = ? AND approval_id = ? "
                        + "AND tenant_id = ? AND owner_user_id = ? AND operation_id = ? AND archived_at IS NULL",
                (rs, rowNum) -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("status", rs.getString("status"));
                    result.put("idempotencyKey", rs.getString("idempotency_key"));
                    result.put("operationId", rs.getString("operation_id"));
                    String data = rs.getString("result_data");
                    result.put("result", data == null ? new LinkedHashMap<>() : JsonUtils.parseObject(data, Map.class));
                    return result;
                }, draftId, approvalId, tenantId, userId, validOperationId);
        if (rows.isEmpty()) return null;

        Map<String, Object> result = rows.get(0);
        Map<String, Object> businessStatus = businessCommitService.findStatus(
                tenantId, userId, draftId, validOperationId);
        if (businessStatus != null) {
            String businessState = String.valueOf(businessStatus.get("status"));
            if ("SUCCEEDED".equals(businessState)) {
                result.put("status", "SUBMITTED");
                result.put("result", businessStatus.get("result"));
            } else if ("PROCESSING".equals(businessState)) {
                result.put("status", "PROCESSING");
            }
        } else if ("SUBMITTING".equals(result.get("status"))) {
            // There is no durable MySQL result yet. The Python Effect owns
            // the UNKNOWN state; this read endpoint only describes what the
            // two Java stores can currently prove.
            result.put("status", "UNKNOWN");
        }
        result.remove("idempotencyKey");
        result.remove("operationId");
        return result;
    }

    @Transactional(transactionManager = "agentEventTransactionManager")
    public Map<String, Object> commit(Long tenantId, Long userId, String draftId, String approvalId,
                                      String expectedOperation, String operationId) {
        String validOperationId = required(operationId, "operationId");
        Map<String, Object> replay = submitted(tenantId, userId, draftId, approvalId, validOperationId);
        if (replay != null) {
            agentApprovalService.completePartyFileExecution(tenantId, userId, approvalId, validOperationId, replay);
            return replay;
        }
        Map<String, Object> businessResult = businessCommitService.findCommittedByDraft(
                tenantId, userId, draftId, approvalId, validOperationId);
        if (businessResult != null) {
            int repaired = jdbcTemplate.update("UPDATE agent_party_file_draft SET status = 'SUBMITTED', result_data = CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP WHERE draft_id = ? AND approval_id = ? AND tenant_id = ? AND owner_user_id = ? AND operation_id = ? AND status IN ('PENDING', 'SUBMITTING')",
                    JsonUtils.toJsonString(businessResult), draftId, approvalId, tenantId, userId, validOperationId);
            if (repaired == 1 || submitted(tenantId, userId, draftId, approvalId, validOperationId) != null) {
                agentApprovalService.completePartyFileExecution(tenantId, userId, approvalId, validOperationId, businessResult);
                return businessResult;
            }
            throw ServiceExceptionUtil.exception0(409, "党务文件业务已提交，但 Agent 结果标记尚未恢复，请稍后重试");
        }
        List<Map<String, Object>> rows = jdbcTemplate.query("UPDATE agent_party_file_draft d SET status = 'SUBMITTING', updated_at = CURRENT_TIMESTAMP WHERE d.draft_id = ? AND d.approval_id = ? AND d.tenant_id = ? AND d.owner_user_id = ? AND d.operation_id = ? AND d.status = 'PENDING' AND d.archived_at IS NULL AND d.expires_at > CURRENT_TIMESTAMP AND EXISTS (SELECT 1 FROM agent_approval a WHERE a.approval_id = d.approval_id AND a.tenant_id = d.tenant_id AND a.approver_user_id = d.owner_user_id AND a.draft_id = d.draft_id AND a.run_id = d.run_id AND a.thread_id = d.thread_id AND a.message_id = d.message_id AND a.operation_id = d.operation_id AND a.draft_type = 'PARTY_FILE' AND a.status = 'APPROVED' AND a.resume_idempotency_key IS NOT NULL) RETURNING d.operation, d.operation_id, d.source_party_file_id, d.source_snapshot::text, d.draft_data::text", (rs, i) -> { Map<String,Object> m=new LinkedHashMap<>(); m.put("operation",rs.getString(1)); m.put("operationId",rs.getString(2)); m.put("sourceId",rs.getObject(3)); m.put("snapshot",JsonUtils.parseObject(rs.getString(4),Map.class)); m.put("draft",JsonUtils.parseObject(rs.getString(5),Map.class)); return m; }, draftId, approvalId, tenantId, userId, validOperationId);
        if (rows.isEmpty()) throw ServiceExceptionUtil.exception0(409, "AGENT_APPROVAL_REQUIRED：党务文件草稿必须先经过 APPROVED 确认");
        Map<String,Object> row=rows.get(0), draft=(Map<String,Object>)row.get("draft");
        draft.put("operationId", validOperationId);
        boolean businessCommitted = false;
        try {
            String operation=String.valueOf(row.get("operation"));
            if (expectedOperation != null && !operation.equalsIgnoreCase(expectedOperation)) throw ServiceExceptionUtil.exception0(409, "PARTY_FILE_OPERATION_MISMATCH：确认操作与草稿不匹配");
            // Permission is checked again after the HITL wait; a revoked role
            // must invalidate the commit instead of allowing an old card to
            // publish or delete a file.
            requirePermission(userId, operation);
            Long sourceId=number(row.get("sourceId"));
            if (!"CREATE".equals(operation)) assertUnchanged(sourceId, (Map<String,Object>)row.get("snapshot"));
            Map<String,Object> result = businessCommitService.commit(tenantId, userId, draftId, draft);
            businessCommitted = true;
            jdbcTemplate.update("UPDATE agent_party_file_draft SET status = 'SUBMITTED', result_data = CAST(? AS jsonb), updated_at = CURRENT_TIMESTAMP WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? AND status = 'SUBMITTING'", JsonUtils.toJsonString(result), draftId, tenantId, userId);
            agentApprovalService.completePartyFileExecution(tenantId, userId, approvalId, validOperationId, result);
            return result;
        } catch (RuntimeException ex) {
            // PostgreSQL owns only the workflow marker. Once the MySQL
            // ledger transaction returned, resetting this row would permit a
            // second real party-file mutation after a cross-database crash.
            if (!businessCommitted) {
                jdbcTemplate.update("UPDATE agent_party_file_draft SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP WHERE draft_id = ? AND tenant_id = ? AND owner_user_id = ? AND operation_id = ? AND status = 'SUBMITTING'", draftId, tenantId, userId, validOperationId);
            }
            throw ex;
        }
    }

    /** The source ID is trusted only from the durable draft row, never from model payload. */
    static PartyFileSaveReqVO asSaveReq(Map<String,Object> draft, Long sourcePartyFileId) {
        // Do not deserialize the complete durable draft into the business VO.
        // The draft intentionally contains Agent provenance (runId/threadId/
        // approvalId, snapshots, idempotency keys, etc.) and Jackson's strict
        // mapper rejects those fields before the real CRUD service is reached.
        // Build the business request field-by-field so the Agent envelope and
        // the OA domain contract remain separate.
        PartyFileSaveReqVO request = new PartyFileSaveReqVO();
        request.setTitle(nullable(draft.get("title")));
        request.setCategoryId(number(draft.get("categoryId")));
        request.setSummary(nullable(draft.get("summary")));
        request.setContent(nullable(draft.get("content")));
        request.setAttachmentFileIds(nullable(draft.get("attachmentFileIds")));
        request.setStorageType(integer(draft.get("storageType")));
        request.setKodSourceId(number(draft.get("kodSourceId")));
        request.setKodFolderPath(nullable(draft.get("kodFolderPath")));
        request.setKodFolderName(nullable(draft.get("kodFolderName")));
        request.setStatus(integer(draft.get("status")));
        request.setPublishTime(parseDateTime(draft.get("publishTime")));
        request.setTargets(targets(draft.get("targets")));
        if (sourcePartyFileId != null) request.setId(sourcePartyFileId);
        return request;
    }

    private static List<PartyFileTargetReqVO> targets(Object value) {
        if (!(value instanceof Collection)) return Collections.emptyList();
        List<PartyFileTargetReqVO> result = new ArrayList<>();
        for (Object item : (Collection<?>) value) {
            if (!(item instanceof Map)) continue;
            Map<?, ?> source = (Map<?, ?>) item;
            PartyFileTargetReqVO target = new PartyFileTargetReqVO();
            Integer targetType = integer(source.get("targetType"));
            Long targetId = number(source.get("targetId"));
            // Accept the unambiguous aliases commonly emitted by the Agent
            // planner while keeping the OA request contract canonical.  A
            // targetType/targetId pair remains the preferred shape; aliases
            // never override an explicitly supplied type.
            if (targetType == null && source.get("userId") != null) {
                targetType = 2; targetId = number(source.get("userId"));
            } else if (targetType == null && source.get("deptId") != null) {
                targetType = 3; targetId = number(source.get("deptId"));
            } else if (targetType == null && source.get("roleId") != null) {
                targetType = 4; targetId = number(source.get("roleId"));
            }
            target.setTargetType(targetType);
            target.setTargetId(targetId);
            result.add(target);
        }
        return result;
    }

    private static Integer integer(Object value) {
        String text = nullable(value);
        if (text == null) return null;
        try { return Integer.valueOf(text); }
        catch (NumberFormatException ex) { throw bad("数字字段格式无效"); }
    }

    private static LocalDateTime parseDateTime(Object value) {
        String text = nullable(value);
        if (text == null) return null;
        // The Agent contract emits the human-readable OA form
        // ``yyyy-MM-dd HH:mm:ss`` while JSON/Java clients commonly send the
        // ISO ``T`` separator. Normalize the former before parsing so the
        // same durable draft can be committed from either surface.
        text = text.trim().replace(' ', 'T');
        try { return LocalDateTime.parse(text); }
        catch (DateTimeParseException ignored) { }
        try { return OffsetDateTime.parse(text).toLocalDateTime(); }
        catch (DateTimeParseException ignored) { }
        try { return Instant.ofEpochMilli(Long.parseLong(text)).atZone(ZoneId.systemDefault()).toLocalDateTime(); }
        catch (NumberFormatException ignored) { throw bad("发布时间格式无效"); }
    }
    private void validatePayload(Map<String,Object> d) {
        required(d,"title"); required(d,"categoryId"); required(d,"storageType");
        String status = required(d,"status");
        if (!"0".equals(status)) throw bad("Agent 文件发布只支持 status=0（正式发布），草稿请在 OA 文件管理中处理");
        required(d,"publishTime");
        if (!(d.get("targets") instanceof List) || ((List<?>)d.get("targets")).isEmpty()) throw bad("党务文件必须指定分发对象");
    }

    private void requirePermission(Long userId, String operation) {
        String permission = "CREATE".equals(operation) ? "system:party-file:create"
                : "UPDATE".equals(operation) ? "system:party-file:update" : "system:party-file:delete";
        if (!permissionService.hasAnyPermissions(userId, permission)) {
            throw ServiceExceptionUtil.exception0(403, "无权执行党务文件" + operation + "操作");
        }
    }
    static void mergeUpdateDefaults(Map<String,Object> draft, Map<String,Object> source) {
        for (String key : Arrays.asList("title", "categoryId", "categoryName", "summary", "content", "attachmentFileIds",
                "storageType", "status", "publishTime", "targets")) {
            Object current = draft.get(key);
            boolean missing = current == null
                    || (current instanceof String && ((String) current).trim().isEmpty())
                    // The Python tool serializes an omitted target list as
                    // []; for UPDATE that means "keep the source targets",
                    // not "clear all recipients".  Let the authorized
                    // source snapshot provide the durable distribution set.
                    || (current instanceof Collection && ((Collection<?>) current).isEmpty());
            if (missing && source.containsKey(key)) draft.put(key, source.get(key));
        }
    }
    private void assertUnchanged(Long id, Map<String,Object> expected) {
        PartyFileRespVO current = partyFileService.getPartyFileDetail(id);
        Map<String, Object> actual = current == null ? null : snapshot(current);
        if (actual == null || !sameSnapshot(actual, expected)) {
            log.warn("party file version conflict: fileId={}, mismatchPath={}, actualTypes={}, expectedTypes={}",
                    id, firstSnapshotMismatch(actual, expected, "$"), valueTypes(actual), valueTypes(expected));
            if (actual != null && expected != null) {
                log.warn("party file version conflict values: actualTargets={}, expectedTargets={}, actualPublishTime={}, expectedPublishTime={}",
                        actual.get("targets"), expected.get("targets"), actual.get("publishTime"), expected.get("publishTime"));
            }
            throw ServiceExceptionUtil.exception0(409,"PARTY_FILE_VERSION_CONFLICT：文件已被修改，请重新读取后确认");
        }
    }

    private static String firstSnapshotMismatch(Object left, Object right, String path) {
        if (left == right) return null;
        if (left == null || right == null) return path;
        if (left instanceof Map && right instanceof Map) {
            Map<?, ?> lm = (Map<?, ?>) left, rm = (Map<?, ?>) right;
            Set<Object> keys = new LinkedHashSet<>(); keys.addAll(lm.keySet()); keys.addAll(rm.keySet());
            for (Object key : keys) {
                String mismatch = firstSnapshotMismatch(lm.get(key), rm.get(key), path + "." + key);
                if (mismatch != null) return mismatch;
            }
            return null;
        }
        if (left instanceof Collection && right instanceof Collection) {
            Iterator<?> li = ((Collection<?>) left).iterator(), ri = ((Collection<?>) right).iterator();
            int index = 0;
            while (li.hasNext() && ri.hasNext()) {
                String mismatch = firstSnapshotMismatch(li.next(), ri.next(), path + "[" + index++ + "]");
                if (mismatch != null) return mismatch;
            }
            return li.hasNext() || ri.hasNext() ? path + ".length" : null;
        }
        return snapshotValueEquals(left, right, path.substring(path.lastIndexOf('.') + 1)) ? null : path;
    }

    private static Map<String, String> valueTypes(Map<String, Object> value) {
        if (value == null) return Collections.emptyMap();
        Map<String, String> types = new LinkedHashMap<>();
        value.forEach((key, item) -> types.put(key, item == null ? "null" : item.getClass().getSimpleName()));
        return types;
    }
    /**
     * Compare snapshots by value, never by JSON text.  The source snapshot is
     * written to PostgreSQL jsonb and read back through a Map; jsonb is free
     * to reorder object keys and its numeric nodes may be materialised as a
     * different Java Number implementation.  String comparison therefore
     * reported false version conflicts for an unchanged file, blocking every
     * UPDATE and DELETE after the ApprovalCard.  This comparison deliberately
     * ignores map order while preserving list order and normalising numbers.
     */
    static boolean sameSnapshot(Map<String,Object> current, Map<String,Object> expected) {
        return snapshotValueEquals(current, expected, null);
    }

    private static boolean snapshotValueEquals(Object left, Object right, String fieldName) {
        if (left == right) return true;
        if (left == null || right == null) return false;

        if (left instanceof Map && right instanceof Map) {
            Map<?, ?> leftMap = (Map<?, ?>) left;
            Map<?, ?> rightMap = (Map<?, ?>) right;
            if (!leftMap.keySet().equals(rightMap.keySet())) return false;
            for (Object key : leftMap.keySet()) {
                if (!snapshotValueEquals(leftMap.get(key), rightMap.get(key), String.valueOf(key))) return false;
            }
            return true;
        }
        if (left instanceof List && right instanceof List) {
            List<?> leftList = (List<?>) left;
            List<?> rightList = (List<?>) right;
            if (leftList.size() != rightList.size()) return false;
            for (int i = 0; i < leftList.size(); i++) {
                if (!snapshotValueEquals(leftList.get(i), rightList.get(i), fieldName)) return false;
            }
            return true;
        }
        if (left instanceof Collection && right instanceof Collection) {
            Iterator<?> leftIterator = ((Collection<?>) left).iterator();
            Iterator<?> rightIterator = ((Collection<?>) right).iterator();
            while (leftIterator.hasNext() && rightIterator.hasNext()) {
                if (!snapshotValueEquals(leftIterator.next(), rightIterator.next(), fieldName)) return false;
            }
            return !leftIterator.hasNext() && !rightIterator.hasNext();
        }
        if (left.getClass().isArray() && right.getClass().isArray()) {
            int leftLength = Array.getLength(left);
            if (leftLength != Array.getLength(right)) return false;
            for (int i = 0; i < leftLength; i++) {
                if (!snapshotValueEquals(Array.get(left, i), Array.get(right, i), fieldName)) return false;
            }
            return true;
        }
        if (left instanceof Number && right instanceof Number) {
            try {
                return new BigDecimal(left.toString()).compareTo(new BigDecimal(right.toString())) == 0;
            } catch (NumberFormatException ignored) {
                return left.equals(right);
            }
        }

        if (isTimeField(fieldName) || isTemporalValue(left) || isTemporalValue(right)) {
            String leftTime = canonicalTime(left);
            String rightTime = canonicalTime(right);
            if (leftTime != null || rightTime != null) {
                return leftTime != null && leftTime.equals(rightTime);
            }
        }

        // Non-temporal strings are business values. Do not coerce them or
        // compare their serialized form, so a changed title/content remains a conflict.
        return Objects.equals(left, right);
    }

    private static boolean isTimeField(String fieldName) {
        if (fieldName == null) return false;
        String normalized = fieldName.toLowerCase(Locale.ROOT);
        return normalized.endsWith("time") || normalized.endsWith("date")
                || normalized.endsWith("datetime") || normalized.endsWith("timestamp")
                || normalized.endsWith("createdat") || normalized.endsWith("updatedat")
                || normalized.endsWith("startat") || normalized.endsWith("endat")
                || normalized.endsWith("expiresat");
    }

    private static boolean isTemporalValue(Object value) {
        return value instanceof Instant || value instanceof ZonedDateTime
                || value instanceof OffsetDateTime || value instanceof LocalDateTime
                || value instanceof LocalDate || value instanceof LocalTime
                || value instanceof Date;
    }

    private static String canonicalTime(Object value) {
        if (value instanceof Instant) return "instant:" + value;
        if (value instanceof ZonedDateTime) return "instant:" + ((ZonedDateTime) value).toInstant();
        if (value instanceof OffsetDateTime) return "instant:" + ((OffsetDateTime) value).toInstant();
        if (value instanceof LocalDateTime) {
            return "instant:" + ((LocalDateTime) value).atZone(ZoneId.systemDefault()).toInstant();
        }
        if (value instanceof LocalDate) return "instant:" + ((LocalDate) value).atStartOfDay(ZoneId.systemDefault()).toInstant();
        if (value instanceof LocalTime) {
            return "local-time:" + ((LocalTime) value).format(DateTimeFormatter.ISO_LOCAL_TIME);
        }
        if (value instanceof Date) return "instant:" + ((Date) value).toInstant();
        // JsonUtils serialises LocalDateTime to epoch milliseconds in this
        // service's ObjectMapper.  The live DTO is temporal while the jsonb
        // snapshot is numeric, so normalise the numeric side to the same
        // instant before comparing.
        if (value instanceof Number) return "instant:" + Instant.ofEpochMilli(((Number) value).longValue());
        if (!(value instanceof CharSequence)) return null;

        String text = value.toString().trim();
        if (text.isEmpty()) return null;
        try { return "instant:" + Instant.ofEpochMilli(Long.parseLong(text)); }
        catch (NumberFormatException ignored) { }
        try { return "instant:" + Instant.parse(text); }
        catch (DateTimeParseException ignored) { }
        try {
            return "instant:" + OffsetDateTime.parse(text, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();
        } catch (DateTimeParseException ignored) { }
        for (DateTimeFormatter formatter : new DateTimeFormatter[]{
                DateTimeFormatter.ISO_LOCAL_DATE_TIME,
                DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"),
                DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")}) {
            try {
                return "instant:" + LocalDateTime.parse(text, formatter)
                        .atZone(ZoneId.systemDefault()).toInstant();
            } catch (DateTimeParseException ignored) { }
        }
        try { return "instant:" + LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE)
                .atStartOfDay(ZoneId.systemDefault()).toInstant(); }
        catch (DateTimeParseException ignored) { }
        try { return "local-time:" + LocalTime.parse(text, DateTimeFormatter.ISO_LOCAL_TIME); }
        catch (DateTimeParseException ignored) { }
        return null;
    }
    private Map<String,Object> snapshot(PartyFileRespVO f) {
        Map<String,Object> m=new LinkedHashMap<>();
        m.put("id",f.getId()); m.put("title",f.getTitle()); m.put("categoryId",f.getCategoryId());
        m.put("summary",f.getSummary()); m.put("content",f.getContent());
        m.put("attachmentFileIds",f.getAttachmentFileIds()); m.put("storageType",f.getStorageType());
        m.put("kodSourceId",f.getKodSourceId()); m.put("kodFolderPath",f.getKodFolderPath());
        m.put("kodFolderName",f.getKodFolderName()); m.put("status",f.getStatus());
        m.put("publishTime",f.getPublishTime()); m.put("targets",targetSnapshot(f.getTargets()));
        return m;
    }

    /**
     * Build the human-facing projection of a durable draft.  The draft keeps
     * raw IDs/enums for the commit boundary, while the projection is the only
     * representation consumed by ApprovalCard fields.
     */
    private void decoratePresentation(Map<String, Object> draft, PartyFileRespVO source) {
        Map<String, Object> presentation = new LinkedHashMap<>();
        String operation = String.valueOf(draft.getOrDefault("operation", "")).toUpperCase(Locale.ROOT);
        presentation.put("operationLabel", "CREATE".equals(operation) ? "发布党务文件"
                : "UPDATE".equals(operation) ? "更新党务文件"
                : "DELETE".equals(operation) ? "删除党务文件" : "党务文件操作");
        if (source != null && nullable(source.getTitle()) != null) {
            presentation.put("sourceTitle", source.getTitle());
        }
        String categoryName = nullable(draft.get("categoryName"));
        if (categoryName == null && source != null) categoryName = nullable(source.getCategoryName());
        if (categoryName == null) {
            Long categoryId = number(draft.get("categoryId"));
            if (categoryId != null) {
                PartyFileCategoryDO category = partyFileCategoryService.getCategory(categoryId);
                categoryName = category == null ? null : category.getName();
            }
        }
        if (categoryName != null) presentation.put("categoryName", categoryName);
        if (draft.get("title") != null) presentation.put("title", draft.get("title"));
        if (draft.get("publishTime") != null) presentation.put("publishTime", draft.get("publishTime"));
        String status = nullable(draft.get("status"));
        if (status != null) presentation.put("statusLabel", partyFileStatusLabel(status));
        String storageType = nullable(draft.get("storageType"));
        if (storageType != null) presentation.put("storageTypeLabel", partyFileStorageLabel(storageType));
        Object targets = draft.get("targets");
        if (!(targets instanceof Collection) && source != null) targets = source.getTargets();
        String distribution = distributionLabel(targets);
        if (distribution != null) presentation.put("distributionLabel", distribution);
        String attachments = attachmentLabel(draft.get("attachmentFileIds"));
        if (attachments != null) presentation.put("attachmentLabel", attachments);
        draft.put("presentation", presentation);
    }

    private static String partyFileStatusLabel(String value) {
        if ("0".equals(value)) return "已发布";
        if ("1".equals(value)) return "草稿";
        return "状态待确认";
    }

    private static String partyFileStorageLabel(String value) {
        if ("1".equals(value)) return "本地存储";
        if ("2".equals(value)) return "可道云存储";
        return "存储方式待确认";
    }

    private static String distributionLabel(Object value) {
        if (!(value instanceof Collection)) return null;
        List<String> labels = new ArrayList<>();
        for (Object item : (Collection<?>) value) {
            Integer type = null;
            String name = null;
            if (item instanceof Map) {
                Map<?, ?> map = (Map<?, ?>) item;
                type = integer(map.get("targetType"));
                name = nullable(map.get("targetName"));
            } else if (item instanceof cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO) {
                cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO target =
                        (cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO) item;
                type = target.getTargetType(); name = nullable(target.getTargetName());
            }
            if (name != null) labels.add(name);
            else if (Objects.equals(type, 1)) labels.add("全员");
            else if (Objects.equals(type, 2)) labels.add("指定用户");
            else if (Objects.equals(type, 3)) labels.add("指定部门");
            else if (Objects.equals(type, 4)) labels.add("指定角色");
            else labels.add("指定分发对象");
        }
        if (labels.isEmpty()) return "未指定";
        return String.join("、", labels);
    }

    private static String attachmentLabel(Object value) {
        String text = nullable(value);
        if (text == null) return "无附件";
        long count = Arrays.stream(text.split(","))
                .map(String::trim).filter(item -> !item.isEmpty()).count();
        return count == 0 ? "无附件" : "已添加附件（" + count + " 个）";
    }

    private static List<Map<String,Object>> targetSnapshot(Collection<?> values) {
        if (values == null) return Collections.emptyList();
        List<Map<String,Object>> result = new ArrayList<>();
        for (Object value : values) {
            if (value instanceof Map) {
                Map<?, ?> source = (Map<?, ?>) value;
                Map<String,Object> target = new LinkedHashMap<>();
                target.put("targetType", source.get("targetType"));
                target.put("targetId", source.get("targetId"));
                if (source.containsKey("targetName")) target.put("targetName", source.get("targetName"));
                result.add(target);
            } else if (value instanceof cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO) {
                cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO source =
                        (cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileTargetRespVO) value;
                Map<String,Object> target = new LinkedHashMap<>();
                target.put("targetType", source.getTargetType()); target.put("targetId", source.getTargetId());
                target.put("targetName", source.getTargetName()); result.add(target);
            }
        }
        return result;
    }
    private Map<String,Object> findPending(Long t,Long u,String k,String r,String th,String m,String operationId){List<Map<String,Object>> x=jdbcTemplate.query("SELECT draft_id, approval_id, draft_data::text FROM agent_party_file_draft WHERE tenant_id=? AND owner_user_id=? AND idempotency_key=? AND run_id=? AND thread_id=? AND message_id=? AND operation_id=? AND status='PENDING' AND archived_at IS NULL AND expires_at>CURRENT_TIMESTAMP",(rs,i)->result(rs.getString(1),rs.getString(2),JsonUtils.parseObject(rs.getString(3),Map.class)),t,u,k,r,th,m,operationId);return x.isEmpty()?null:x.get(0);}
    private Map<String,Object> submitted(Long t,Long u,String d,String a,String operationId){List<Map<String,Object>> x=jdbcTemplate.query("SELECT result_data::text FROM agent_party_file_draft WHERE draft_id=? AND approval_id=? AND tenant_id=? AND owner_user_id=? AND operation_id=? AND status='SUBMITTED' AND archived_at IS NULL",(rs,i)->JsonUtils.parseObject(rs.getString(1),Map.class),d,a,t,u,operationId);return x.isEmpty()?null:x.get(0);}
    private Map<String,Object> result(String d,String a,Map<String,Object> data){Map<String,Object> r=new LinkedHashMap<>();r.put("draftId",d);r.put("approvalId",a);r.put("draft",data);return r;}
    private String required(Map<String,Object> d,String k){return required(nullable(d.get(k)), k);}
    private String required(String value, String key){String v=nullable(value);if(v==null)throw bad("缺少 "+key);return v;}
    private static String nullable(Object v){String s=v==null?null:String.valueOf(v).trim();return s==null||s.isEmpty()||"null".equalsIgnoreCase(s)?null:s;} private static Long number(Object v){try{String s=nullable(v);return s==null?null:Long.valueOf(s);}catch(NumberFormatException e){throw bad("文件编号必须是数字");}} private static RuntimeException bad(String m){return ServiceExceptionUtil.exception0(400,m);}
}
