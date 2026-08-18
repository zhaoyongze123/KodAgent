package cn.iocoder.yudao.module.system.service.auth;

import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.web.core.util.WebFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.KodDeptSyncRespVO;
import cn.iocoder.yudao.module.system.controller.admin.dept.vo.dept.DeptSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodDeptSyncDO;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodSsoUserBindDO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.auth.KodDeptSyncMapper;
import cn.iocoder.yudao.module.system.dal.mysql.auth.KodSsoUserBindMapper;
import cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper;
import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoProperties;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.AUTH_KOD_SSO_BAD_REQUEST;

/**
 * 可道云组织树同步实现。
 *
 * 可道云插件负责其内部 source/user_group 的原子维护，本服务只维护本地部门镜像、稳定映射和登录账号部门。
 */
@Service
@Validated
@Slf4j
public class KodDeptSyncServiceImpl implements KodDeptSyncService {

    private static final String SYNC_SUCCESS = "SUCCESS";

    @Resource
    private KodSsoProperties kodSsoProperties;
    @Resource
    private KodDeptSyncMapper kodDeptSyncMapper;
    @Resource
    private KodSsoUserBindMapper kodSsoUserBindMapper;
    @Resource
    private DeptMapper deptMapper;
    @Resource
    private DeptService deptService;
    @Resource
    private AdminUserService adminUserService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public KodDeptSyncRespVO sync(Long tenantId) {
        validateConfig();
        if (tenantId == null) {
            tenantId = kodSsoProperties.getTenantId();
        }
        Long finalTenantId = tenantId;
        KodDeptSyncData data;
        try {
            data = requestKodSync();
        } catch (RuntimeException ex) {
            log.error("可道云组织同步请求失败，tenantId={}", finalTenantId, ex);
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "可道云组织同步失败: " + ex.getMessage());
        }
        if (!Boolean.TRUE.equals(data.getSuccess())) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST,
                    "可道云组织同步失败: " + StrUtil.blankToDefault(data.getMessage(), "插件返回失败"));
        }
        List<KodDeptSyncData.Group> groups = data.getGroups();
        if (groups == null || groups.isEmpty()) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "可道云组织同步失败: 未返回部门树，已拒绝覆盖本地组织");
        }

        Map<String, Long> localDeptByKodGroup = syncDepartments(finalTenantId, groups);
        syncBoundUsers(finalTenantId, data.getUsers(), localDeptByKodGroup, groups);
        disableRemovedDepartments(finalTenantId, groups);

        KodDeptSyncRespVO result = new KodDeptSyncRespVO();
        result.setSuccess(true);
        result.setDepartmentCount(defaultInt(data.getDepartmentCount(), groups.size()));
        result.setUserCount(defaultInt(data.getUserCount(), data.getUsers() == null ? 0 : data.getUsers().size()));
        result.setCreatedSourceCount(defaultInt(data.getCreatedSourceCount(), 0));
        result.setRevokedPermissionCount(defaultInt(data.getRevokedPermissionCount(), 0));
        result.setMessage(StrUtil.blankToDefault(data.getMessage(), "可道云组织同步完成"));
        return result;
    }

    private Map<String, Long> syncDepartments(Long tenantId, List<KodDeptSyncData.Group> groups) {
        Map<String, KodDeptSyncData.Group> groupMap = new LinkedHashMap<>();
        for (KodDeptSyncData.Group group : groups) {
            if (group != null && StrUtil.isNotBlank(group.getGroupId())) {
                groupMap.put(group.getGroupId(), group);
            }
        }
        Map<String, Long> localDeptByKodGroup = new LinkedHashMap<>();
        String kodRootGroupId = StrUtil.blankToDefault(kodSsoProperties.getOrganizationSyncRootGroupId(), "1");
        Set<String> pending = new HashSet<>(groupMap.keySet());
        for (int pass = 0; !pending.isEmpty() && pass <= groupMap.size(); pass++) {
            boolean progressed = false;
            for (String kodGroupId : new ArrayList<>(pending)) {
                KodDeptSyncData.Group group = groupMap.get(kodGroupId);
                String parentGroupId = normalizeParent(group.getParentGroupId());
                Long parentDeptId = parentGroupId == null || kodRootGroupId.equals(parentGroupId)
                        ? DeptDO.PARENT_ID_ROOT : localDeptByKodGroup.get(parentGroupId);
                if (parentDeptId == null) {
                    continue;
                }
                Long localDeptId = upsertLocalDepartment(tenantId, group, parentDeptId);
                localDeptByKodGroup.put(kodGroupId, localDeptId);
                pending.remove(kodGroupId);
                progressed = true;
            }
            if (!progressed) {
                throw exception(AUTH_KOD_SSO_BAD_REQUEST, "可道云组织树存在无法解析的父部门或循环引用");
            }
        }
        return localDeptByKodGroup;
    }

    private Long upsertLocalDepartment(Long tenantId, KodDeptSyncData.Group group, Long parentDeptId) {
        String name = StrUtil.maxLength(StrUtil.trimToEmpty(group.getName()), 50);
        if (StrUtil.isBlank(name)) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "可道云部门缺少名称: " + group.getGroupId());
        }
        Integer localStatus = isKodEnabled(group.getStatus())
                ? CommonStatusEnum.ENABLE.getStatus() : CommonStatusEnum.DISABLE.getStatus();
        KodDeptSyncDO mapping = kodDeptSyncMapper.selectByKodGroupId(tenantId, group.getGroupId());
        DeptDO dept = mapping == null || mapping.getLocalDeptId() == null
                ? null : deptMapper.selectById(mapping.getLocalDeptId());
        if (dept == null) {
            dept = deptMapper.selectByParentIdAndName(parentDeptId, name);
        }
        if (dept == null) {
            DeptSaveReqVO req = new DeptSaveReqVO();
            req.setParentId(parentDeptId);
            req.setName(name);
            req.setSort(defaultInt(group.getSort(), 0));
            req.setStatus(localStatus);
            Long deptId = runAsSystemOperator(() -> deptService.createDept(req));
            if (deptId != null) {
                dept = deptService.getDept(deptId);
            }
            if (dept == null) {
                dept = deptMapper.selectByParentIdAndName(parentDeptId, name);
            }
        } else if (!Objects.equals(dept.getParentId(), parentDeptId)
                || !Objects.equals(dept.getName(), name)
                || !Objects.equals(dept.getSort(), defaultInt(group.getSort(), 0))
                || !Objects.equals(dept.getStatus(), localStatus)) {
            DeptSaveReqVO req = new DeptSaveReqVO();
            req.setId(dept.getId());
            req.setParentId(parentDeptId);
            req.setName(name);
            req.setSort(defaultInt(group.getSort(), 0));
            req.setLeaderUserId(dept.getLeaderUserId());
            req.setPhone(dept.getPhone());
            req.setEmail(dept.getEmail());
            req.setStatus(localStatus);
            runAsSystemOperator(() -> {
                deptService.updateDept(req);
                return null;
            });
        }
        if (dept == null) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "本地部门创建失败: " + name);
        }
        if (mapping == null) {
            mapping = new KodDeptSyncDO();
            mapping.setTenantId(tenantId);
            mapping.setKodGroupId(group.getGroupId());
            mapping.setCreator("kod-dept-sync");
            mapping.setCreateTime(java.time.LocalDateTime.now());
        }
        mapping.setLocalDeptId(dept.getId());
        mapping.setKodSourceId(group.getSourceId());
        mapping.setKodParentGroupId(normalizeParent(group.getParentGroupId()));
        mapping.setGroupName(name);
        mapping.setStatus(localStatus);
        mapping.setLastSyncStatus(SYNC_SUCCESS);
        mapping.setLastSyncMessage("同步完成");
        mapping.setUpdater("kod-dept-sync");
        mapping.setUpdateTime(java.time.LocalDateTime.now());
        if (mapping.getId() == null) {
            kodDeptSyncMapper.insert(mapping);
        } else {
            kodDeptSyncMapper.updateById(mapping);
        }
        return dept.getId();
    }

    private void syncBoundUsers(Long tenantId, List<KodDeptSyncData.UserGroups> users,
                                Map<String, Long> localDeptByKodGroup, List<KodDeptSyncData.Group> groups) {
        if (users == null) {
            return;
        }
        Map<String, Integer> depthMap = new HashMap<>();
        Map<String, String> parentMap = new HashMap<>();
        for (KodDeptSyncData.Group group : groups) {
            parentMap.put(group.getGroupId(), normalizeParent(group.getParentGroupId()));
        }
        for (String groupId : localDeptByKodGroup.keySet()) {
            depthMap.put(groupId, depth(groupId, parentMap));
        }
        for (KodDeptSyncData.UserGroups item : users) {
            if (item == null || StrUtil.isBlank(item.getUserId()) || item.getGroupIds() == null) {
                continue;
            }
            String leafGroupId = item.getGroupIds().stream()
                    .filter(localDeptByKodGroup::containsKey)
                    .max(Comparator.comparingInt(groupId -> depthMap.getOrDefault(groupId, 0)))
                    .orElse(null);
            if (leafGroupId == null) {
                continue;
            }
            KodSsoUserBindDO bind = kodSsoUserBindMapper.selectByKodUserId(item.getUserId());
            if (bind == null || bind.getUserId() == null) {
                continue;
            }
            AdminUserDO user = adminUserService.getUser(bind.getUserId());
            Long targetDeptId = localDeptByKodGroup.get(leafGroupId);
            if (user != null && !Objects.equals(user.getDeptId(), targetDeptId)) {
                runAsSystemOperator(() -> {
                    adminUserService.updateUserDept(user.getId(), targetDeptId);
                    return null;
                });
            }
        }
    }

    private void disableRemovedDepartments(Long tenantId, List<KodDeptSyncData.Group> groups) {
        Set<String> activeGroupIds = new HashSet<>();
        for (KodDeptSyncData.Group group : groups) {
            activeGroupIds.add(group.getGroupId());
        }
        for (KodDeptSyncDO mapping : kodDeptSyncMapper.selectListByTenantId(tenantId)) {
            if (activeGroupIds.contains(mapping.getKodGroupId())) {
                continue;
            }
            mapping.setStatus(CommonStatusEnum.DISABLE.getStatus());
            mapping.setLastSyncStatus(SYNC_SUCCESS);
            mapping.setLastSyncMessage("可道云部门已移除，保留历史文件并停用本地镜像");
            kodDeptSyncMapper.updateById(mapping);
            if (mapping.getLocalDeptId() != null) {
                DeptDO dept = deptMapper.selectById(mapping.getLocalDeptId());
                if (dept != null && !CommonStatusEnum.DISABLE.getStatus().equals(dept.getStatus())) {
                    DeptSaveReqVO req = new DeptSaveReqVO();
                    req.setId(dept.getId());
                    req.setParentId(dept.getParentId());
                    req.setName(dept.getName());
                    req.setSort(dept.getSort());
                    req.setLeaderUserId(dept.getLeaderUserId());
                    req.setPhone(dept.getPhone());
                    req.setEmail(dept.getEmail());
                    req.setStatus(CommonStatusEnum.DISABLE.getStatus());
                    runAsSystemOperator(() -> {
                        deptService.updateDept(req);
                        return null;
                    });
                }
            }
        }
    }

    private KodDeptSyncData requestKodSync() {
        String accessToken = kodSsoProperties.getOrganizationSyncAccessToken();
        if (StrUtil.isBlank(accessToken)) {
            accessToken = loginOrganizationAdmin();
        }
        if (StrUtil.isBlank(accessToken)) {
            throw new IllegalStateException("未配置可道云组织管理员令牌或账号密码");
        }
        String endpoint = resolveEndpoint();
        String rootGroupId = StrUtil.blankToDefault(kodSsoProperties.getOrganizationSyncRootGroupId(), "1");
        String url = endpoint + (endpoint.contains("?") ? "&" : "?")
                + "accessToken=" + HttpUtils.encodeUtf8(accessToken)
                + "&rootGroupId=" + HttpUtils.encodeUtf8(rootGroupId)
                + "&dryRun=0&confirm=1";
        try (HttpResponse response = HttpRequest.get(url)
                .timeout(defaultInt(kodSsoProperties.getOrganizationSyncTimeout(), 15000))
                .execute()) {
            String body = response.body();
            KodDeptSyncData data = JsonUtils.parseObject(body, KodDeptSyncData.class);
            if (data == null) {
                throw new IllegalStateException("可道云同步插件返回为空");
            }
            return data;
        }
    }

    private String loginOrganizationAdmin() {
        if (StrUtil.hasBlank(kodSsoProperties.getOrganizationSyncUsername(),
                kodSsoProperties.getOrganizationSyncPassword())) {
            return null;
        }
        String url = getKodServerBaseUrl() + "?user/index/loginSubmit&name="
                + HttpUtils.encodeUtf8(kodSsoProperties.getOrganizationSyncUsername())
                + "&password=" + HttpUtils.encodeUtf8(kodSsoProperties.getOrganizationSyncPassword());
        try (HttpResponse response = HttpRequest.get(url)
                .timeout(defaultInt(kodSsoProperties.getOrganizationSyncTimeout(), 15000))
                .execute()) {
            com.fasterxml.jackson.databind.JsonNode root = JsonUtils.parseTree(response.body());
            if (root == null || !root.path("code").asBoolean(false)) {
                throw new IllegalStateException("可道云组织管理员登录失败");
            }
            String token = extractLoginAccessToken(root);
            return StrUtil.isBlank(token) ? null : token;
        }
    }

    /**
     * Kodbox loginSubmit returns the short status in data and the usable
     * login ticket in info. Newer deployments may return accessToken directly
     * or wrap it in data, so keep the extraction compatible with all shapes.
     */
    private String extractLoginAccessToken(com.fasterxml.jackson.databind.JsonNode root) {
        String token = root.path("info").asText();
        if (StrUtil.isBlank(token)) {
            token = root.path("accessToken").asText();
        }
        if (StrUtil.isBlank(token) && root.path("data").isObject()) {
            token = root.path("data").path("accessToken").asText();
        }
        if (StrUtil.isBlank(token) && root.path("data").isTextual()
                && !StrUtil.equalsIgnoreCase(root.path("data").asText(), "ok")) {
            token = root.path("data").asText();
        }
        return token;
    }

    private String resolveEndpoint() {
        if (StrUtil.isNotBlank(kodSsoProperties.getOrganizationSyncEndpoint())) {
            return kodSsoProperties.getOrganizationSyncEndpoint();
        }
        return getKodServerBaseUrl() + "index.php?plugin/oaDeptSync/sync";
    }

    private String getKodServerBaseUrl() {
        return StrUtil.removeSuffix(StrUtil.blankToDefault(kodSsoProperties.getServerBaseUrl(), kodSsoProperties.getBaseUrl()), "/") + "/";
    }

    private void validateConfig() {
        if (!Boolean.TRUE.equals(kodSsoProperties.getEnabled())
                || !Boolean.TRUE.equals(kodSsoProperties.getOrganizationSyncEnabled())) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "可道云组织同步未启用");
        }
        if (StrUtil.isBlank(kodSsoProperties.getBaseUrl())) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "缺少可道云 baseUrl 配置");
        }
    }

    private <T> T runAsSystemOperator(Supplier<T> supplier) {
        HttpServletRequest request = ServletUtils.getRequest();
        org.springframework.security.core.Authentication oldAuthentication = SecurityFrameworkUtils.getAuthentication();
        Long oldRequestUserId = WebFrameworkUtils.getLoginUserId(request);
        Integer oldRequestUserType = WebFrameworkUtils.getLoginUserType(request);
        try {
            LoginUser operator = new LoginUser();
            operator.setId(1L);
            operator.setTenantId(TenantContextHolder.getTenantId());
            operator.setUserType(cn.iocoder.yudao.framework.common.enums.UserTypeEnum.ADMIN.getValue());
            if (request != null) {
                SecurityFrameworkUtils.setLoginUser(operator, request);
            } else {
                org.springframework.security.core.context.SecurityContextHolder.getContext().setAuthentication(
                        new org.springframework.security.authentication.UsernamePasswordAuthenticationToken(
                                operator, null, Collections.emptyList()));
            }
            return supplier.get();
        } finally {
            if (oldAuthentication != null) {
                org.springframework.security.core.context.SecurityContextHolder.getContext().setAuthentication(oldAuthentication);
            } else {
                org.springframework.security.core.context.SecurityContextHolder.clearContext();
            }
            if (request != null) {
                WebFrameworkUtils.setLoginUserId(request, oldRequestUserId);
                WebFrameworkUtils.setLoginUserType(request, oldRequestUserType);
            }
        }
    }

    private static String normalizeParent(String parentGroupId) {
        return StrUtil.isBlank(parentGroupId) || "0".equals(parentGroupId) ? null : parentGroupId;
    }

    private static boolean isKodEnabled(Integer status) {
        return status == null || status == 1;
    }

    private static int depth(String groupId, Map<String, String> parentMap) {
        int result = 0;
        Set<String> seen = new HashSet<>();
        String current = groupId;
        while (current != null && seen.add(current)) {
            result++;
            current = parentMap.get(current);
        }
        return result;
    }

    private static int defaultInt(Integer value, int defaultValue) {
        return value == null ? defaultValue : value;
    }
}
