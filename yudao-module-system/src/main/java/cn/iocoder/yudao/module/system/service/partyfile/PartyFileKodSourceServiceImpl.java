package cn.iocoder.yudao.module.system.service.partyfile;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodFolderRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodSourcePageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodSourceSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileDO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodSourceDO;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileKodSourceMapper;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileMapper;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Validated
public class PartyFileKodSourceServiceImpl implements PartyFileKodSourceService {

    private static final int KOD_HTTP_CONNECT_TIMEOUT_MILLIS = 3_000;
    private static final int KOD_HTTP_READ_TIMEOUT_MILLIS = 10_000;

    private static final int TOKEN_EXPIRE_MINUTES = 240;

    @Resource
    private PartyFileKodSourceMapper partyFileKodSourceMapper;
    @Resource
    private PartyFileMapper partyFileMapper;

    @Override
    public Long create(PartyFileKodSourceSaveReqVO reqVO) {
        validateNameUnique(reqVO.getName(), null);
        PartyFileKodSourceDO source = buildSource(reqVO, null);
        if (Boolean.TRUE.equals(source.getIsDefault())) {
            clearDefaultFlag();
        }
        partyFileKodSourceMapper.insert(source);
        return source.getId();
    }

    @Override
    public void update(PartyFileKodSourceSaveReqVO reqVO) {
        PartyFileKodSourceDO exists = validateExists(reqVO.getId());
        validateNameUnique(reqVO.getName(), reqVO.getId());
        PartyFileKodSourceDO updateObj = buildSource(reqVO, exists);
        if (Boolean.TRUE.equals(updateObj.getIsDefault())) {
            clearDefaultFlag();
        } else if (Boolean.TRUE.equals(exists.getIsDefault())) {
            updateObj.setIsDefault(false);
        }
        partyFileKodSourceMapper.updateById(updateObj);
    }

    @Override
    public void delete(Long id) {
        validateExists(id);
        List<PartyFileDO> usingFiles = partyFileMapper.selectListByKodSourceId(id);
        if (CollUtil.isNotEmpty(usingFiles)) {
            throw exception(PARTY_FILE_KOD_SOURCE_IN_USE);
        }
        partyFileKodSourceMapper.deleteById(id);
    }

    @Override
    public PartyFileKodSourceDO get(Long id) {
        return validateExists(id);
    }

    @Override
    public List<PartyFileKodSourceDO> getSimpleList() {
        return partyFileKodSourceMapper.selectEnabledList();
    }

    @Override
    public PageResult<PartyFileKodSourceDO> getPage(PartyFileKodSourcePageReqVO reqVO) {
        return partyFileKodSourceMapper.selectPage(reqVO);
    }

    @Override
    public List<PartyFileKodFolderRespVO> getFolderTree(Long id) {
        PartyFileKodSourceDO source = validateExists(id);
        return Collections.singletonList(buildFolderNode(source.getRootFolderName(), source.getRootFolderPath(),
                loadChildren(source, source.getRootFolderPath())));
    }

    public interface KodAccessTokenCallback<T> {
        T execute(String accessToken) throws Exception;
    }

    public PartyFileKodSourceDO getEnabledSource(Long id) {
        PartyFileKodSourceDO source = validateExists(id);
        if (!Objects.equals(source.getStatus(), CommonStatusEnum.ENABLE.getStatus())) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID,
                    "可道云目录来源【" + buildSourceLabel(source) + "】已停用");
        }
        return source;
    }

    private List<PartyFileKodFolderRespVO> loadChildren(PartyFileKodSourceDO source, String path) {
        JsonNode current = requestKodFolderList(source, path);
        JsonNode folderList = current.path("folderList");
        if (!folderList.isArray() || folderList.isEmpty()) {
            return Collections.emptyList();
        }
        List<PartyFileKodFolderRespVO> result = new ArrayList<>();
        for (JsonNode folder : folderList) {
            String childPath = firstNonBlank(folder, "path", "sourceID");
            String childName = firstNonBlank(folder, "name", "pathDisplay");
            if (StrUtil.isBlank(childPath) || StrUtil.isBlank(childName)) {
                continue;
            }
            result.add(buildFolderNode(childName, childPath, loadChildren(source, childPath)));
        }
        return result;
    }

    private PartyFileKodFolderRespVO buildFolderNode(String name, String path, List<PartyFileKodFolderRespVO> children) {
        PartyFileKodFolderRespVO node = new PartyFileKodFolderRespVO();
        node.setKey(path);
        node.setTitle(name);
        node.setValue(path);
        node.setPath(path);
        node.setChildren(children);
        return node;
    }

    public JsonNode requestKodFolderList(PartyFileKodSourceDO source, String path) {
        try {
            return executeWithValidAccessToken(source, accessToken -> {
                String url = source.getBaseUrl()
                        + "?explorer/list/path&accessToken=" + HttpUtils.encodeUtf8(accessToken)
                        + "&path=" + HttpUtils.encodeUtf8(normalizeFolderPath(path));
                return requestKodJson(url, "目录返回为空");
            });
        } catch (Exception ex) {
            if (ex instanceof RuntimeException) {
                throw (RuntimeException) ex;
            }
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED, buildSourceErrorMessage(source, ex.getMessage()));
        }
    }

    public <T> T executeWithValidAccessToken(PartyFileKodSourceDO source, KodAccessTokenCallback<T> callback) throws Exception {
        PartyFileKodSourceDO current = source;
        String accessToken = getValidAccessToken(current);
        try {
            return callback.execute(accessToken);
        } catch (ServiceException ex) {
            if (!shouldRetryByRefreshing(current, ex)) {
                throw ex;
            }
            PartyFileKodSourceDO refreshed = refreshAccessToken(validateExists(current.getId()));
            return callback.execute(refreshed.getAccessToken());
        }
    }

    public boolean isKodAuthFailure(String message) {
        return StrUtil.containsAny(StrUtil.blankToDefault(message, ""), "您尚未登录", "登录已失效", "请先登录");
    }

    private boolean isKodFailure(JsonNode root, JsonNode data) {
        if (root.has("code")) {
            JsonNode code = root.get("code");
            if (code.isBoolean()) {
                return !code.booleanValue();
            }
            return "false".equalsIgnoreCase(code.asText()) || "10001".equals(code.asText());
        }
        return data.has("code") && !"true".equalsIgnoreCase(data.get("code").asText());
    }

    private String extractKodMessage(JsonNode root, JsonNode data) {
        String message = firstNonBlank(root, "data", "msg", "message", "info");
        if (StrUtil.isBlank(message) && data != null && data.isObject()) {
            message = firstNonBlank(data, "msg", "message", "info");
        }
        return StrUtil.blankToDefault(message, "可道云接口返回失败");
    }

    private String firstNonBlank(JsonNode node, String... fieldNames) {
        if (node == null || node.isMissingNode()) {
            return null;
        }
        for (String fieldName : fieldNames) {
            JsonNode value = node.get(fieldName);
            if (value != null && !value.isNull()) {
                String text = value.asText();
                if (StrUtil.isNotBlank(text)) {
                    return text;
                }
            }
        }
        return null;
    }

    private void validateNameUnique(String name, Long id) {
        PartyFileKodSourceDO exists = partyFileKodSourceMapper.selectByName(name);
        if (exists != null && !Objects.equals(exists.getId(), id)) {
            throw exception(PARTY_FILE_KOD_SOURCE_NAME_DUPLICATE);
        }
    }

    private PartyFileKodSourceDO validateExists(Long id) {
        PartyFileKodSourceDO source = partyFileKodSourceMapper.selectById(id);
        if (source == null) {
            throw exception(PARTY_FILE_KOD_SOURCE_NOT_FOUND);
        }
        return source;
    }

    private void clearDefaultFlag() {
        PartyFileKodSourceDO defaultSource = partyFileKodSourceMapper.selectDefault();
        if (defaultSource == null) {
            return;
        }
        defaultSource.setIsDefault(false);
        partyFileKodSourceMapper.updateById(defaultSource);
    }

    private String normalizeBaseUrl(String baseUrl) {
        return StrUtil.addSuffixIfNot(StrUtil.trim(baseUrl), "/");
    }

    private String normalizeFolderPath(String path) {
        String normalized = StrUtil.trim(path);
        if (StrUtil.isBlank(normalized)) {
            throw exception(PARTY_FILE_KOD_FOLDER_PATH_INVALID);
        }
        return normalized;
    }

    private PartyFileKodSourceDO buildSource(PartyFileKodSourceSaveReqVO reqVO, PartyFileKodSourceDO exists) {
        PartyFileKodSourceDO source = BeanUtils.toBean(reqVO, PartyFileKodSourceDO.class);
        source.setBaseUrl(normalizeBaseUrl(reqVO.getBaseUrl()));
        source.setRootFolderPath(normalizeFolderPath(reqVO.getRootFolderPath()));
        source.setIsDefault(Boolean.TRUE.equals(reqVO.getIsDefault()));
        source.setServiceUsername(StrUtil.trimToNull(reqVO.getServiceUsername()));
        source.setServicePassword(resolveServicePassword(reqVO, exists));
        source.setAccessToken(StrUtil.trimToEmpty(reqVO.getAccessToken()));
        if (StrUtil.isBlank(source.getServiceUsername())) {
            source.setServicePassword(null);
            source.setTokenExpireTime(null);
        }
        validateAuthConfig(source);
        if (hasServiceCredential(source)) {
            source = refreshAccessToken(source);
        } else {
            source.setTokenExpireTime(null);
        }
        return source;
    }

    private String resolveServicePassword(PartyFileKodSourceSaveReqVO reqVO, PartyFileKodSourceDO exists) {
        String password = StrUtil.trimToNull(reqVO.getServicePassword());
        if (password != null) {
            return password;
        }
        if (exists == null) {
            return null;
        }
        if (StrUtil.equals(StrUtil.trimToNull(reqVO.getServiceUsername()), exists.getServiceUsername())) {
            return exists.getServicePassword();
        }
        return null;
    }

    private void validateAuthConfig(PartyFileKodSourceDO source) {
        boolean hasServiceUsername = StrUtil.isNotBlank(source.getServiceUsername());
        boolean hasServicePassword = StrUtil.isNotBlank(source.getServicePassword());
        boolean hasAccessToken = StrUtil.isNotBlank(source.getAccessToken());
        if (hasServiceUsername ^ hasServicePassword) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
        }
        if (!hasAccessToken && !hasServiceUsername) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
        }
    }

    private String getValidAccessToken(PartyFileKodSourceDO source) {
        if (hasServiceCredential(source) && isTokenExpired(source)) {
            source = refreshAccessToken(source);
        }
        if (StrUtil.isBlank(source.getAccessToken())) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID,
                    "可道云目录来源【" + buildSourceLabel(source) + "】缺少 accessToken");
        }
        return source.getAccessToken();
    }

    private boolean isTokenExpired(PartyFileKodSourceDO source) {
        if (StrUtil.isBlank(source.getAccessToken())) {
            return true;
        }
        LocalDateTime expireTime = source.getTokenExpireTime();
        return expireTime == null || expireTime.minusMinutes(5).isBefore(LocalDateTime.now());
    }

    private boolean hasServiceCredential(PartyFileKodSourceDO source) {
        return StrUtil.isNotBlank(source.getServiceUsername()) && StrUtil.isNotBlank(source.getServicePassword());
    }

    private boolean shouldRetryByRefreshing(PartyFileKodSourceDO source, ServiceException ex) {
        return hasServiceCredential(source)
                && Objects.equals(ex.getCode(), PARTY_FILE_KOD_REQUEST_FAILED.getCode())
                && isKodAuthFailure(ex.getMessage());
    }

    private PartyFileKodSourceDO refreshAccessToken(PartyFileKodSourceDO source) {
        if (!hasServiceCredential(source)) {
            return source;
        }
        String loginUrl = source.getBaseUrl() + "index.php?user/index/loginSubmit";
        JsonNode loginResp;
        try (HttpResponse response = HttpRequest.post(loginUrl)
                .form("name", source.getServiceUsername())
                .form("password", source.getServicePassword())
                .setConnectionTimeout(KOD_HTTP_CONNECT_TIMEOUT_MILLIS)
                .setReadTimeout(KOD_HTTP_READ_TIMEOUT_MILLIS)
                .execute()) {
            loginResp = parseJsonResponse(response, "可道云登录返回为空");
        } catch (Exception ex) {
            throw wrapKodException(source, ex);
        }
        String loginToken = firstNonBlank(loginResp, "info", "accessToken", "data");
        if (StrUtil.isBlank(loginToken) || isKodFailure(loginResp, loginResp.path("data"))) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                    buildSourceErrorMessage(source, extractKodMessage(loginResp, loginResp.path("data"))));
        }

        String checkUrl = source.getBaseUrl() + "?user/sso/apiCheckToken"
                + "&accessToken=" + HttpUtils.encodeUtf8(loginToken)
                + "&appName=" + HttpUtils.encodeUtf8(source.getAppName());
        JsonNode checkResp = requestKodJson(checkUrl, "可道云换取 accessToken 返回为空");
        String finalAccessToken = firstNonBlank(checkResp, "accessToken");
        if (StrUtil.isBlank(finalAccessToken)) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                    buildSourceErrorMessage(source, "可道云未返回最终 accessToken"));
        }
        source.setAccessToken(finalAccessToken);
        source.setTokenExpireTime(LocalDateTime.now().plusMinutes(TOKEN_EXPIRE_MINUTES));
        if (source.getId() != null) {
            partyFileKodSourceMapper.updateById(source);
        }
        return source;
    }

    private JsonNode requestKodJson(String url, String emptyMessage) {
        try (HttpResponse response = HttpRequest.get(url)
                .setConnectionTimeout(KOD_HTTP_CONNECT_TIMEOUT_MILLIS)
                .setReadTimeout(KOD_HTTP_READ_TIMEOUT_MILLIS)
                .execute()) {
            return parseJsonResponse(response, emptyMessage);
        } catch (Exception ex) {
            throw wrapKodException(null, ex);
        }
    }

    private JsonNode parseJsonResponse(HttpResponse response, String emptyMessage) {
        String body = response.body();
        JsonNode root = JsonUtils.parseTree(body);
        if (root == null || root.isMissingNode()) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED, emptyMessage);
        }
        JsonNode data = root.path("data");
        if (isKodFailure(root, data)) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED, extractKodMessage(root, data));
        }
        return data.isObject() ? data : root;
    }

    public String buildSourceLabel(PartyFileKodSourceDO source) {
        if (source == null) {
            return "未知来源";
        }
        String sourceName = StrUtil.blankToDefault(source.getName(), "未命名来源");
        return sourceName + "(ID=" + source.getId() + ")";
    }

    public String buildSourceErrorMessage(PartyFileKodSourceDO source, String detail) {
        String message = StrUtil.blankToDefault(StrUtil.trim(detail), "未知错误");
        if (isKodAuthFailure(message)) {
            message = "鉴权已失效或未登录，请检查服务账号/密码，系统会在请求时自动刷新 token。原始信息：" + message;
        }
        return "目录来源【" + buildSourceLabel(source) + "】" + message;
    }

    private ServiceException wrapKodException(PartyFileKodSourceDO source, Exception ex) {
        if (ex instanceof ServiceException) {
            return (ServiceException) ex;
        }
        return exception(PARTY_FILE_KOD_REQUEST_FAILED, buildSourceErrorMessage(source, ex.getMessage()));
    }
}
