package cn.iocoder.yudao.module.system.service.auth;

import cn.hutool.core.lang.UUID;
import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.enums.UserTypeEnum;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.framework.security.core.LoginUser;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.web.core.util.WebFrameworkUtils;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.AuthLoginRespVO;
import cn.iocoder.yudao.module.system.controller.admin.dept.vo.dept.DeptSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.user.vo.profile.UserProfileUpdateReqVO;
import cn.iocoder.yudao.module.system.controller.admin.user.vo.user.UserSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodSsoUserBindDO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.auth.KodSsoUserBindMapper;
import cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper;
import cn.iocoder.yudao.module.system.enums.logger.LoginLogTypeEnum;
import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoProperties;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import com.fasterxml.jackson.databind.JsonNode;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Validated
@Slf4j
public class KodSsoServiceImpl implements KodSsoService {

    private static final String EXCHANGE_CODE_PARAM = "kodSsoCode";
    private static final String AUTO_CREATED_USER_PASSWORD = "admin123";

    @Resource
    private KodSsoProperties kodSsoProperties;
    @Resource
    private KodSsoUserBindMapper kodSsoUserBindMapper;
    @Resource
    private DeptMapper deptMapper;
    @Resource
    private AdminUserService adminUserService;
    @Resource
    private AdminAuthService adminAuthService;
    @Resource
    private PermissionService permissionService;
    @Resource
    private DeptService deptService;

    private final Map<String, ExchangeCodeCacheItem> exchangeCodeCache = new ConcurrentHashMap<>();

    @Override
    public String buildAuthorizeRedirectUrl(HttpServletRequest request, String redirectUri) {
        validateEnabled();
        validateBaseConfig();
        String finalRedirectUri = resolveRedirectUri(redirectUri, false);
        String callbackUrl = buildCallbackUrl(request, finalRedirectUri);
        return normalizeBaseUrl(kodSsoProperties.getBaseUrl())
                + "?user/sso/apiLogin&appName=" + HttpUtils.encodeUtf8(kodSsoProperties.getAppName())
                + "&callbackUrl=" + HttpUtils.encodeUtf8(callbackUrl);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public AuthLoginRespVO loginByKodToken(String kodAccessToken) {
        KodSsoResolvedUser resolvedUser = resolveOrCreateUser(kodAccessToken);
        return runWithSystemOperatorContext(() -> adminAuthService.createLoginToken(
                resolvedUser.getUserId(), resolvedUser.getUsername(), LoginLogTypeEnum.LOGIN_KOD_SSO));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public String buildClientRedirectUrl(String kodAccessToken, String redirectUri) {
        String finalRedirectUri = resolveRedirectUri(redirectUri, true);
        KodSsoResolvedUser resolvedUser = resolveOrCreateUser(kodAccessToken);
        String exchangeCode = IdUtil.fastSimpleUUID();
        exchangeCodeCache.put(exchangeCode, new ExchangeCodeCacheItem(
                resolvedUser.getUserId(), resolvedUser.getUsername(),
                LocalDateTime.now().plus(kodSsoProperties.getExchangeCodeExpire())));
        return appendExchangeCode(finalRedirectUri, exchangeCode);
    }

    @Override
    public AuthLoginRespVO exchangeCode(String code) {
        ExchangeCodeCacheItem cacheItem = exchangeCodeCache.remove(code);
        if (cacheItem == null || cacheItem.getExpireTime().isBefore(LocalDateTime.now())) {
            throw exception(AUTH_KOD_SSO_EXCHANGE_CODE_NOT_FOUND);
        }
        return runWithSystemOperatorContext(() -> adminAuthService.createLoginToken(
                cacheItem.getUserId(), cacheItem.getUsername(), LoginLogTypeEnum.LOGIN_KOD_SSO));
    }

    private KodSsoResolvedUser resolveOrCreateUser(String kodAccessToken) {
        validateEnabled();
        validateBaseConfig();
        KodUserProfile profile = fetchKodUserProfile(kodAccessToken);
        AdminUserDO matchedUser = matchExistingUser(profile);
        if (matchedUser != null) {
            upsertBind(matchedUser.getId(), profile);
            syncLocalProfile(matchedUser, profile);
            syncLocalDept(matchedUser, profile);
            syncLocalRoles(matchedUser.getId(), profile);
            return new KodSsoResolvedUser(matchedUser.getId(), matchedUser.getUsername());
        }
        Long userId = createLocalUser(profile);
        upsertBind(userId, profile);
        AdminUserDO user = adminUserService.getUser(userId);
        return new KodSsoResolvedUser(userId, user.getUsername());
    }

    private KodUserProfile fetchKodUserProfile(String kodAccessToken) {
        if (StrUtil.isBlank(kodAccessToken)) {
            throw exception(AUTH_KOD_SSO_TOKEN_INVALID, "缺少可道云访问令牌");
        }
        String url = normalizeBaseUrl(kodSsoProperties.getBaseUrl())
                + "?user/sso/apiCheckToken&accessToken=" + HttpUtils.encodeUtf8(kodAccessToken)
                + "&appName=" + HttpUtils.encodeUtf8(kodSsoProperties.getAppName());
        String response = HttpUtils.get(url, Collections.emptyMap());
        if (!JsonUtils.isJsonObject(response)) {
            log.warn("可道云校验返回非 JSON，body={}", response);
            throw exception(AUTH_KOD_SSO_TOKEN_INVALID, "可道云校验返回异常");
        }
        JsonNode root = JsonUtils.parseTree(response);
        if (isFailureResponse(root)) {
            throw exception(AUTH_KOD_SSO_TOKEN_INVALID, extractErrorMessage(root));
        }
        JsonNode payload = root.has("data") && root.get("data").isObject() ? root.get("data") : root;
        String kodUserId = firstNonBlank(payload, "userID", "userId", "id");
        String kodUsername = firstNonBlank(payload, "name", "username", "userName");
        String kodNickname = firstNonBlank(payload, "nickName", "nickname", "displayName", "name");
        String email = firstNonBlank(payload, "email");
        String mobile = firstNonBlank(payload, "mobile", "phone", "tel");
        // apiCheckToken 的最小返回只包含用户身份资料，但不同的 KodBox
        // 版本/部署会附带 groupInfo。部门不是权限来源，能够安全地作为
        // 组织同步的可选输入；缺失时保持空路径，不得据此清空已有部门。
        // 角色仍必须通过明确的 userRoleMappings/defaultRoleIds 配置或本地
        // 绑定决定，不能根据可道云返回的 roleID/isRoot 推断本地权限。
        Long kodRoleId = null;
        List<KodDeptNode> deptPath = extractDeptPath(payload);
        boolean isRoot = false;
        if (StrUtil.isAllBlank(kodUserId, kodUsername)) {
            throw exception(AUTH_KOD_SSO_TOKEN_INVALID, "可道云返回缺少用户唯一标识");
        }
        if (StrUtil.isBlank(kodUserId)) {
            kodUserId = kodUsername;
        }
        return new KodUserProfile(kodUserId, kodUsername, StrUtil.blankToDefault(kodNickname, kodUsername),
                email, mobile, kodRoleId, deptPath, isRoot, response);
    }

    private boolean isFailureResponse(JsonNode root) {
        if (root == null || root.isMissingNode()) {
            return true;
        }
        if (root.has("code")) {
            JsonNode code = root.get("code");
            if (code.isBoolean()) {
                return !code.booleanValue();
            }
            String codeText = code.asText();
            return "10001".equals(codeText) || "false".equalsIgnoreCase(codeText);
        }
        return false;
    }

    private String extractErrorMessage(JsonNode root) {
        String message = firstNonBlank(root, "data", "info", "message", "msg");
        return StrUtil.blankToDefault(message, "可道云校验失败");
    }

    private Long createLocalUser(KodUserProfile profile) {
        UserSaveReqVO createReqVO = new UserSaveReqVO();
        createReqVO.setUsername(resolveLocalUsername(profile));
        createReqVO.setNickname(StrUtil.blankToDefault(StrUtil.maxLength(profile.getKodNickname(), 30), createReqVO.getUsername()));
        createReqVO.setEmail(sanitizeEmail(profile.getEmail()));
        createReqVO.setMobile(sanitizeMobile(profile.getMobile()));
        createReqVO.setDeptId(resolveOrCreateDeptId(profile));
        createReqVO.setPassword(AUTO_CREATED_USER_PASSWORD);
        Long userId = runWithSystemOperatorContext(() -> adminUserService.createUser(createReqVO));
        syncLocalRoles(userId, profile);
        return userId;
    }

    private <T> T runWithSystemOperatorContext(Supplier<T> supplier) {
        HttpServletRequest request = ServletUtils.getRequest();
        Authentication oldAuthentication = SecurityFrameworkUtils.getAuthentication();
        Long oldRequestUserId = WebFrameworkUtils.getLoginUserId(request);
        Integer oldRequestUserType = WebFrameworkUtils.getLoginUserType(request);
        try {
            LoginUser systemOperator = new LoginUser();
            systemOperator.setId(1L);
            systemOperator.setUserType(UserTypeEnum.ADMIN.getValue());
            systemOperator.setTenantId(kodSsoProperties.getTenantId());
            if (request != null) {
                SecurityFrameworkUtils.setLoginUser(systemOperator, request);
            } else {
                SecurityContextHolder.getContext().setAuthentication(
                        new UsernamePasswordAuthenticationToken(systemOperator, null, Collections.emptyList()));
            }
            return supplier.get();
        } finally {
            if (oldAuthentication != null) {
                SecurityContextHolder.getContext().setAuthentication(oldAuthentication);
            } else {
                SecurityContextHolder.clearContext();
            }
            if (request != null) {
                WebFrameworkUtils.setLoginUserId(request, oldRequestUserId);
                WebFrameworkUtils.setLoginUserType(request, oldRequestUserType);
            }
        }
    }

    private void createBind(Long userId, KodUserProfile profile) {
        KodSsoUserBindDO bind = new KodSsoUserBindDO();
        bind.setUserId(userId);
        bind.setKodUserId(profile.getKodUserId());
        bind.setKodUsername(profile.getKodUsername());
        bind.setKodNickname(profile.getKodNickname());
        bind.setRawProfileJson(profile.getRawProfileJson());
        kodSsoUserBindMapper.insert(bind);
    }

    /**
     * hash 路由场景下，前端真实 query 位于 # 后，交换码必须追加到 fragment 内部。
     */
    private String appendExchangeCode(String redirectUri, String exchangeCode) {
        if (!StrUtil.contains(redirectUri, "#")) {
            return HttpUtils.append(redirectUri, Collections.singletonMap(EXCHANGE_CODE_PARAM, exchangeCode), null, false);
        }
        String[] parts = StrUtil.splitToArray(redirectUri, '#', 2);
        String baseUrl = parts[0];
        String fragment = parts.length > 1 ? parts[1] : StrUtil.EMPTY;
        String fragmentWithCode = HttpUtils.append(fragment, Collections.singletonMap(EXCHANGE_CODE_PARAM, exchangeCode), null, false);
        return baseUrl + "#" + fragmentWithCode;
    }

    private void upsertBind(Long userId, KodUserProfile profile) {
        KodSsoUserBindDO bind = kodSsoUserBindMapper.selectByUserId(userId);
        if (bind == null) {
            KodSsoUserBindDO bindByKodUserId = kodSsoUserBindMapper.selectByKodUserId(profile.getKodUserId());
            if (bindByKodUserId != null) {
                bindByKodUserId.setUserId(userId);
                syncBind(bindByKodUserId, profile);
                return;
            }
            KodSsoUserBindDO bindByKodUsername = kodSsoUserBindMapper.selectByKodUsername(profile.getKodUsername());
            if (bindByKodUsername != null) {
                bindByKodUsername.setUserId(userId);
                syncBind(bindByKodUsername, profile);
                return;
            }
            createBind(userId, profile);
            return;
        }
        bind.setKodUserId(profile.getKodUserId());
        syncBind(bind, profile);
    }

    private void syncBind(KodSsoUserBindDO bind, KodUserProfile profile) {
        boolean changed = false;
        if (!StrUtil.equals(bind.getKodUserId(), profile.getKodUserId())) {
            bind.setKodUserId(profile.getKodUserId());
            changed = true;
        }
        if (!StrUtil.equals(bind.getKodUsername(), profile.getKodUsername())) {
            bind.setKodUsername(profile.getKodUsername());
            changed = true;
        }
        if (!StrUtil.equals(bind.getKodNickname(), profile.getKodNickname())) {
            bind.setKodNickname(profile.getKodNickname());
            changed = true;
        }
        if (!StrUtil.equals(bind.getRawProfileJson(), profile.getRawProfileJson())) {
            bind.setRawProfileJson(profile.getRawProfileJson());
            changed = true;
        }
        if (changed) {
            kodSsoUserBindMapper.updateById(bind);
        }
    }

    private AdminUserDO matchExistingUser(KodUserProfile profile) {
        KodSsoUserBindDO bind = findBind(profile);
        if (bind != null) {
            AdminUserDO bindUser = adminUserService.getUser(bind.getUserId());
            if (bindUser != null) {
                return bindUser;
            }
            log.warn("可道云绑定记录已失效，kodUserId={}, kodUsername={}, userId={}",
                    profile.getKodUserId(), profile.getKodUsername(), bind.getUserId());
        }
        return adminUserService.getUserByUsername(resolveLocalUsername(profile));
    }

    private KodSsoUserBindDO findBind(KodUserProfile profile) {
        if (StrUtil.isNotBlank(profile.getKodUsername())) {
            KodSsoUserBindDO bindByKodUsername = kodSsoUserBindMapper.selectByKodUsername(profile.getKodUsername());
            if (bindByKodUsername != null) {
                return bindByKodUsername;
            }
        }
        if (StrUtil.isBlank(profile.getKodUserId())) {
            return null;
        }
        return kodSsoUserBindMapper.selectByKodUserId(profile.getKodUserId());
    }

    private void syncLocalProfile(AdminUserDO user, KodUserProfile profile) {
        UserProfileUpdateReqVO updateReqVO = new UserProfileUpdateReqVO();
        updateReqVO.setNickname(resolveProfileNickname(user, profile));
        updateReqVO.setEmail(resolveProfileEmail(user, profile));
        updateReqVO.setMobile(resolveProfileMobile(user, profile));
        if (Objects.equals(updateReqVO.getNickname(), user.getNickname())
                && Objects.equals(updateReqVO.getEmail(), user.getEmail())
                && Objects.equals(updateReqVO.getMobile(), user.getMobile())) {
            return;
        }
        runWithSystemOperatorContext(() -> {
            adminUserService.updateUserProfile(user.getId(), updateReqVO);
            return null;
        });
    }

    private String resolveProfileNickname(AdminUserDO user, KodUserProfile profile) {
        return StrUtil.blankToDefault(StrUtil.maxLength(profile.getKodNickname(), 30), user.getNickname());
    }

    private String resolveProfileEmail(AdminUserDO user, KodUserProfile profile) {
        String email = sanitizeEmail(profile.getEmail());
        return StrUtil.isNotBlank(email) ? email : user.getEmail();
    }

    private String resolveProfileMobile(AdminUserDO user, KodUserProfile profile) {
        String mobile = sanitizeMobile(profile.getMobile());
        return StrUtil.isNotBlank(mobile) ? mobile : user.getMobile();
    }

    private void syncLocalDept(AdminUserDO user, KodUserProfile profile) {
        Long targetDeptId = resolveOrCreateDeptId(profile);
        if (Objects.equals(user.getDeptId(), targetDeptId)) {
            return;
        }
        runWithSystemOperatorContext(() -> {
            adminUserService.updateUserDept(user.getId(), targetDeptId);
            return null;
        });
    }

    private Long resolveOrCreateDeptId(KodUserProfile profile) {
        if (CollUtil.isEmpty(profile.getDeptPath())) {
            return null;
        }
        Long parentId = DeptDO.PARENT_ID_ROOT;
        Long leafDeptId = null;
        int sort = 0;
        for (KodDeptNode deptNode : profile.getDeptPath()) {
            String deptName = sanitizeDeptName(deptNode.getGroupName());
            if (StrUtil.isBlank(deptName)) {
                continue;
            }
            DeptDO dept = deptMapper.selectByParentIdAndName(parentId, deptName);
            if (dept == null) {
                DeptSaveReqVO createReqVO = new DeptSaveReqVO();
                createReqVO.setParentId(parentId);
                createReqVO.setName(deptName);
                createReqVO.setSort(++sort);
                createReqVO.setStatus(CommonStatusEnum.ENABLE.getStatus());
                Long deptId = runWithSystemOperatorContext(() -> deptService.createDept(createReqVO));
                dept = deptService.getDept(deptId);
                if (dept == null) {
                    dept = deptMapper.selectByParentIdAndName(parentId, deptName);
                }
                if (dept == null) {
                    throw exception(AUTH_KOD_SSO_BAD_REQUEST, "创建或查询部门失败: " + deptName);
                }
            } else if (!Objects.equals(dept.getStatus(), CommonStatusEnum.ENABLE.getStatus())) {
                DeptSaveReqVO updateReqVO = new DeptSaveReqVO();
                updateReqVO.setId(dept.getId());
                updateReqVO.setParentId(dept.getParentId());
                updateReqVO.setName(dept.getName());
                updateReqVO.setSort(dept.getSort());
                updateReqVO.setLeaderUserId(dept.getLeaderUserId());
                updateReqVO.setPhone(dept.getPhone());
                updateReqVO.setEmail(dept.getEmail());
                updateReqVO.setStatus(CommonStatusEnum.ENABLE.getStatus());
                runWithSystemOperatorContext(() -> {
                    deptService.updateDept(updateReqVO);
                    return null;
                });
                dept.setStatus(CommonStatusEnum.ENABLE.getStatus());
            }
            parentId = dept.getId();
            leafDeptId = dept.getId();
        }
        return leafDeptId;
    }

    private String resolveLocalUsername(KodUserProfile profile) {
        String username = StrUtil.trimToEmpty(profile.getKodUsername());
        if (StrUtil.isBlank(username)) {
            username = StrUtil.trimToEmpty(profile.getKodUserId());
        }
        if (StrUtil.isBlank(username)) {
            throw exception(AUTH_KOD_SSO_TOKEN_INVALID, "可道云返回缺少用户账号");
        }
        return StrUtil.maxLength(username, 30);
    }

    private String sanitizeDeptName(String name) {
        return StrUtil.maxLength(StrUtil.trim(name), 30);
    }

    private String sanitizeEmail(String email) {
        if (StrUtil.isBlank(email) || !StrUtil.contains(email, "@")) {
            return null;
        }
        return StrUtil.maxLength(email, 50);
    }

    private String sanitizeMobile(String mobile) {
        if (StrUtil.isBlank(mobile)) {
            return null;
        }
        String digits = mobile.replaceAll("[^0-9]", "");
        if (digits.length() != 11) {
            return null;
        }
        return digits;
    }

    private String resolveRedirectUri(String redirectUri, boolean required) {
        String finalRedirectUri = StrUtil.blankToDefault(redirectUri, kodSsoProperties.getRedirectUri());
        if (StrUtil.isBlank(finalRedirectUri)) {
            if (required) {
                throw exception(AUTH_KOD_SSO_REDIRECT_URI_INVALID);
            }
            return null;
        }
        if (!StrUtil.startWithAnyIgnoreCase(finalRedirectUri, "http://", "https://")) {
            throw exception(AUTH_KOD_SSO_REDIRECT_URI_INVALID);
        }
        return finalRedirectUri;
    }

    private String buildCallbackUrl(HttpServletRequest request, String redirectUri) {
        String callbackUrl;
        if (StrUtil.isNotBlank(kodSsoProperties.getCallbackBaseUrl())) {
            callbackUrl = StrUtil.removeSuffix(kodSsoProperties.getCallbackBaseUrl(), "/")
                    + "/admin-api/system/auth/kod-sso/callback";
        } else {
            callbackUrl = request.getRequestURL().toString().replace("/start", "/callback");
        }
        if (StrUtil.isBlank(redirectUri)) {
            return callbackUrl;
        }
        return HttpUtils.append(callbackUrl, Collections.singletonMap("redirectUri", redirectUri), null, false);
    }

    private void validateEnabled() {
        if (!Boolean.TRUE.equals(kodSsoProperties.getEnabled())) {
            throw exception(AUTH_KOD_SSO_DISABLED);
        }
    }

    private void validateBaseConfig() {
        if (StrUtil.hasBlank(kodSsoProperties.getBaseUrl(), kodSsoProperties.getAppName())) {
            throw exception(AUTH_KOD_SSO_BAD_REQUEST, "缺少 baseUrl 或 appName 配置");
        }
    }

    private String normalizeBaseUrl(String baseUrl) {
        return StrUtil.removeSuffix(baseUrl, "/") + "/";
    }

    private void syncLocalRoles(Long userId, KodUserProfile profile) {
        Set<Long> currentRoleIds = permissionService.getUserRoleIdListByUserId(userId);
        Set<Long> targetRoleIds = new HashSet<>(CollUtil.emptyIfNull(currentRoleIds));
        targetRoleIds.removeAll(getManagedLocalRoleIds());

        Long mappedRoleId = resolveLocalRoleId(profile);
        if (mappedRoleId != null) {
            targetRoleIds.add(mappedRoleId);
        } else if (CollUtil.isNotEmpty(kodSsoProperties.getDefaultRoleIds())) {
            targetRoleIds.addAll(kodSsoProperties.getDefaultRoleIds());
            log.warn("可道云用户 {} 未匹配到角色映射，回退使用默认角色 {}", profile.getKodUserId(),
                    kodSsoProperties.getDefaultRoleIds());
        } else {
            // 可道云返回的角色字段缺失或出现新角色时，不能把本地已有角色清空。
            // 否则一次 SSO 登录就会造成权限降级，且用户只能看到“没有该操作权限”。
            log.warn("可道云用户 {} 未匹配到角色映射，且未配置默认角色，保留现有本地角色", profile.getKodUserId());
            return;
        }

        if (!Objects.equals(targetRoleIds, currentRoleIds)) {
            runWithSystemOperatorContext(() -> {
                permissionService.assignUserRole(userId, targetRoleIds);
                return null;
            });
        }
    }

    private Set<Long> getManagedLocalRoleIds() {
        Set<Long> roleIds = new HashSet<>();
        addRoleId(roleIds, kodSsoProperties.getLocalSuperAdminRoleId());
        addRoleId(roleIds, kodSsoProperties.getLocalDeptAdminRoleId());
        addRoleId(roleIds, kodSsoProperties.getLocalCommonRoleId());
        return roleIds;
    }

    private Long resolveLocalRoleId(KodUserProfile profile) {
        Map<String, Long> mappings = kodSsoProperties.getUserRoleMappings();
        if (mappings == null || mappings.isEmpty()) {
            return null;
        }
        Long roleId = mappings.get(profile.getKodUserId());
        if (roleId == null) {
            roleId = mappings.get(profile.getKodUsername());
        }
        return roleId;
    }

    private void addRoleId(Set<Long> roleIds, Long roleId) {
        if (roleId != null && roleId > 0) {
            roleIds.add(roleId);
        }
    }

    private String firstNonBlank(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.get(field);
            if (value != null && !value.isNull() && StrUtil.isNotBlank(value.asText())) {
                return value.asText();
            }
        }
        return null;
    }

    private Long firstLong(JsonNode node, String... fields) {
        String value = firstNonBlank(node, fields);
        if (StrUtil.isBlank(value) || !StrUtil.isNumeric(value)) {
            return null;
        }
        return Long.valueOf(value);
    }

    private List<KodDeptNode> extractDeptPath(JsonNode node) {
        JsonNode groupInfo = node.get("groupInfo");
        if (groupInfo == null || !groupInfo.isArray() || groupInfo.isEmpty()) {
            return Collections.emptyList();
        }
        List<KodDeptNode> deptPath = new ArrayList<>();
        for (JsonNode groupNode : groupInfo) {
            String groupName = firstNonBlank(groupNode, "groupName", "name");
            if (StrUtil.isBlank(groupName)) {
                continue;
            }
            deptPath.add(new KodDeptNode(firstNonBlank(groupNode, "groupID", "groupId", "id"), groupName));
        }
        return deptPath;
    }

    private boolean firstBoolean(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.get(field);
            if (value == null || value.isNull()) {
                continue;
            }
            if (value.isBoolean()) {
                return value.booleanValue();
            }
            String text = value.asText();
            if (StrUtil.isBlank(text)) {
                continue;
            }
            if ("1".equals(text) || "true".equalsIgnoreCase(text)) {
                return true;
            }
            if ("0".equals(text) || "false".equalsIgnoreCase(text)) {
                return false;
            }
        }
        return false;
    }

    @Data
    @AllArgsConstructor
    private static class KodUserProfile {
        private String kodUserId;
        private String kodUsername;
        private String kodNickname;
        private String email;
        private String mobile;
        private Long kodRoleId;
        private List<KodDeptNode> deptPath;
        private boolean root;
        private String rawProfileJson;
    }

    @Data
    @AllArgsConstructor
    private static class KodDeptNode {
        private String groupId;
        private String groupName;
    }

    @Data
    @AllArgsConstructor
    private static class KodSsoResolvedUser {
        private Long userId;
        private String username;
    }

    @Data
    @AllArgsConstructor
    private static class ExchangeCodeCacheItem {
        private Long userId;
        private String username;
        private LocalDateTime expireTime;
    }

}
