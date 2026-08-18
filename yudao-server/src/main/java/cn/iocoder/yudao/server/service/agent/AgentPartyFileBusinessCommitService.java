package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import javax.sql.DataSource;
import java.util.Collections;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * MySQL commit boundary for one party-file Effect.
 *
 * <p>This is deliberately a party-file adapter, not a second generic
 * workflow engine. The small ledger is needed because the Draft/Approval
 * facts live in PostgreSQL while the party-file mutation lives in MySQL. The
 * ledger and the business mutation are committed in one MySQL transaction so
 * a process crash can be reconciled without executing the mutation twice.</p>
 */
@Service
public class AgentPartyFileBusinessCommitService {

    @Resource
    private DataSource dataSource;
    @Resource
    private PartyFileService partyFileService;

    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initialize() {
        jdbcTemplate = new JdbcTemplate(dataSource);
    }

    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> commit(Long tenantId, Long userId, String draftId,
                                      Map<String, Object> draft) {
        String operation = required(draft, "operation").toUpperCase(Locale.ROOT);
        if (!Arrays.asList("CREATE", "UPDATE", "DELETE").contains(operation)) {
            throw ServiceExceptionUtil.exception0(400, "不支持的党务文件操作");
        }
        String idempotencyKey = required(draft, "idempotencyKey");
        String operationId = required(draft, "operationId");

        // Insert-or-read avoids a race between two resumed workers. The row
        // is locked before the business call, so the second worker observes
        // the durable result instead of issuing another mutation.
        jdbcTemplate.update("INSERT INTO agent_party_file_commit "
                        + "(tenant_id, owner_user_id, draft_id, approval_id, operation_id, idempotency_key, operation, status) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, 'PROCESSING') "
                        + "ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)",
                tenantId, userId, draftId, required(draft, "approvalId"), operationId,
                idempotencyKey, operation);
        Map<String, Object> current = findByIdempotencyForUpdate(tenantId, userId, idempotencyKey);
        if (current == null) {
            throw ServiceExceptionUtil.exception0(500, "党务文件提交台账不可用");
        }
        if (!same(draftId, current.get("draftId"))
                || !same(required(draft, "approvalId"), current.get("approvalId"))
                || !same(operationId, current.get("operationId"))
                || !same(operation, current.get("operation"))) {
            throw ServiceExceptionUtil.exception0(409,
                    "PARTY_FILE_IDEMPOTENCY_CONFLICT：幂等键已绑定其他党务文件提交");
        }
        if ("SUCCEEDED".equals(current.get("status"))) {
            return resultData(current);
        }
        jdbcTemplate.update("UPDATE agent_party_file_commit SET status = 'PROCESSING', "
                        + "update_time = CURRENT_TIMESTAMP WHERE id = ?",
                current.get("id"));

        Long sourceId = number(draft.get("sourcePartyFileId"));
        Long fileId;
        if ("CREATE".equals(operation)) {
            fileId = partyFileService.createPartyFile(AgentPartyFileDraftService.asSaveReq(draft, null));
        } else {
            if (sourceId == null) {
                throw ServiceExceptionUtil.exception0(400, "修改或删除党务文件必须指定 sourcePartyFileId");
            }
            fileId = sourceId;
            if ("UPDATE".equals(operation)) {
                partyFileService.updatePartyFile(AgentPartyFileDraftService.asSaveReq(draft, sourceId));
            } else {
                partyFileService.deletePartyFile(sourceId);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("success", true);
        result.put("fileId", fileId);
        result.put("operation", operation);
        result.put("message", "CREATE".equals(operation) ? "党务文件已发布"
                : "UPDATE".equals(operation) ? "党务文件已更新" : "党务文件已删除");
        jdbcTemplate.update("UPDATE agent_party_file_commit SET status = 'SUCCEEDED', "
                        + "party_file_id = ?, result_data = ?, update_time = CURRENT_TIMESTAMP WHERE id = ?",
                fileId, JsonUtils.toJsonString(result), current.get("id"));
        return result;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findCommittedByDraft(Long tenantId, Long userId, String draftId,
                                                    String approvalId, String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, result_data FROM agent_party_file_commit "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND draft_id = ? "
                        + "AND approval_id = ? AND operation_id = ? "
                        + "ORDER BY id DESC LIMIT 1",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, draftId, approvalId, operationId);
        if (rows.isEmpty() || !"SUCCEEDED".equals(rows.get(0).get("status"))) return null;
        return resultData(rows.get(0));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findCommittedByIdempotency(Long tenantId, Long userId,
                                                           String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.trim().isEmpty()) return null;
        Map<String, Object> row = findByIdempotency(tenantId, userId, idempotencyKey);
        if (row == null || !"SUCCEEDED".equals(row.get("status"))) return null;
        return resultData(row);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> findStatus(Long tenantId, Long userId, String draftId,
                                          String operationId) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, idempotency_key, result_data FROM agent_party_file_commit "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND draft_id = ? "
                        + "AND operation_id = ? ORDER BY id DESC LIMIT 1",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("idempotencyKey", rs.getString("idempotency_key"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, draftId, operationId);
        if (rows.isEmpty()) return null;
        Map<String, Object> row = rows.get(0);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", row.get("status"));
        result.put("result", parseResult(row.get("result")));
        return result;
    }

    private Map<String, Object> findByIdempotencyForUpdate(Long tenantId, Long userId,
                                                            String idempotencyKey) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT id, draft_id, approval_id, operation_id, operation, status, result_data FROM agent_party_file_commit "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ? FOR UPDATE",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", rs.getLong("id"));
                    row.put("draftId", rs.getString("draft_id"));
                    row.put("approvalId", rs.getString("approval_id"));
                    row.put("operationId", rs.getString("operation_id"));
                    row.put("operation", rs.getString("operation"));
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, idempotencyKey);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private Map<String, Object> findByIdempotency(Long tenantId, Long userId,
                                                   String idempotencyKey) {
        List<Map<String, Object>> rows = jdbcTemplate.query(
                "SELECT status, result_data FROM agent_party_file_commit "
                        + "WHERE tenant_id = ? AND owner_user_id = ? AND idempotency_key = ?",
                (rs, rowNum) -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("status", rs.getString("status"));
                    row.put("result", rs.getString("result_data"));
                    return row;
                }, tenantId, userId, idempotencyKey);
        return rows.isEmpty() ? null : rows.get(0);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> resultData(Map<String, Object> row) {
        Map<String, Object> result = parseResult(row.get("result"));
        return result == null ? Collections.emptyMap() : result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseResult(Object value) {
        if (value == null) return new LinkedHashMap<>();
        Map<String, Object> result = JsonUtils.parseObject(String.valueOf(value), Map.class);
        return result == null ? new LinkedHashMap<>() : result;
    }

    private String required(Map<String, Object> draft, String key) {
        String value = nullable(draft.get(key));
        if (value == null) throw ServiceExceptionUtil.exception0(400, "缺少 " + key);
        return value;
    }

    private String nullable(Object value) {
        String result = value == null ? null : String.valueOf(value).trim();
        return result == null || result.isEmpty() || "null".equalsIgnoreCase(result) ? null : result;
    }

    private boolean same(Object expected, Object actual) {
        return String.valueOf(expected == null ? "" : expected)
                .equals(String.valueOf(actual == null ? "" : actual));
    }

    private Long number(Object value) {
        String text = nullable(value);
        if (text == null) return null;
        try {
            return Long.valueOf(text);
        } catch (NumberFormatException ex) {
            throw ServiceExceptionUtil.exception0(400, "sourcePartyFileId 必须是数字");
        }
    }
}
