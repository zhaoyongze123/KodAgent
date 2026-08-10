package cn.iocoder.yudao.module.system.service.partyfile;

import cn.hutool.core.date.DateUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.infra.controller.admin.file.vo.file.FileCreateReqVO;
import cn.iocoder.yudao.module.infra.dal.dataobject.file.FileDO;
import cn.iocoder.yudao.module.infra.framework.file.core.utils.FileTypeUtils;
import cn.iocoder.yudao.module.infra.dal.mysql.file.FileMapper;
import cn.iocoder.yudao.module.infra.framework.file.core.client.FileClient;
import cn.iocoder.yudao.module.infra.service.file.FileConfigService;
import cn.iocoder.yudao.module.infra.service.file.FileService;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileAttachmentUploadRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodFileRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodSelectFileReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodSelectReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodUserFilesReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodUserSelectReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodFolderRespVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodAttachmentDO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodSourceDO;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileKodAttachmentMapper;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileStorageTypeEnum;
import cn.iocoder.yudao.module.system.service.auth.KodSsoService;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.multipart.MultipartFile;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_ATTACHMENT_NOT_FOUND;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_KOD_REQUEST_FAILED;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_STORAGE_CONFIG_INVALID;

@Service
@Validated
public class PartyFileAttachmentServiceImpl implements PartyFileAttachmentService {

    private static final int KOD_FOLDER_CONNECT_TIMEOUT_MILLIS = 3_000;
    private static final int KOD_FOLDER_READ_TIMEOUT_MILLIS = 10_000;
    @Resource
    private FileService fileService;
    @Resource
    private FileMapper fileMapper;
    @Resource
    private FileConfigService fileConfigService;
    @Resource
    private PartyFileKodSourceServiceImpl partyFileKodSourceService;
    @Resource
    private PartyFileKodAttachmentMapper partyFileKodAttachmentMapper;
    @Resource
    private KodSsoService kodSsoService;
    @Resource
    private cn.iocoder.yudao.module.system.service.filepreview.FilePreviewConverter filePreviewConverter;

    @Override
    public PartyFileAttachmentUploadRespVO uploadAttachment(MultipartFile file, Integer storageType, Long kodSourceId,
                                                            String kodFolderPath) throws Exception {
        if (file == null || file.isEmpty()) {
            throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
        }
        if (PartyFileStorageTypeEnum.isKod(storageType)) {
            return uploadKodAttachment(file, kodSourceId, kodFolderPath);
        }
        return uploadLocalAttachment(file);
    }

    @Override
    public List<PartyFileKodFileRespVO> getKodFiles(Long kodSourceId, String kodFolderPath) {
        if (kodSourceId == null || StrUtil.isBlank(kodFolderPath)) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
        }
        PartyFileKodSourceDO source = partyFileKodSourceService.getEnabledSource(kodSourceId);
        JsonNode current = partyFileKodSourceService.requestKodFolderList(source, kodFolderPath);
        JsonNode fileList = current.path("fileList");
        if (!fileList.isArray() || fileList.isEmpty()) {
            return new ArrayList<>();
        }
        List<PartyFileKodFileRespVO> result = new ArrayList<>();
        for (JsonNode fileNode : fileList) {
            PartyFileKodFileRespVO file = new PartyFileKodFileRespVO();
            file.setName(firstNonBlank(fileNode, null, "name"));
            file.setPath(firstNonBlank(fileNode, null, "path"));
            file.setPathDisplay(firstNonBlank(fileNode, null, "pathDisplay"));
            file.setSize(fileNode.has("size") ? fileNode.path("size").asLong(0L) : 0L);
            file.setType(FileTypeUtils.getMineType(file.getName()));
            if (StrUtil.isBlank(file.getName()) || StrUtil.isBlank(file.getPath())) {
                continue;
            }
            result.add(file);
        }
        return result;
    }

    @Override
    public List<PartyFileAttachmentUploadRespVO> selectKodFiles(PartyFileKodSelectReqVO reqVO) {
        if (reqVO.getKodSourceId() == null || StrUtil.isBlank(reqVO.getKodFolderPath())) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
        }
        partyFileKodSourceService.getEnabledSource(reqVO.getKodSourceId());
        List<PartyFileAttachmentUploadRespVO> result = new ArrayList<>();
        for (PartyFileKodSelectFileReqVO file : reqVO.getFiles()) {
            result.add(bindKodAttachment(reqVO.getKodSourceId(), reqVO.getKodFolderPath(), file));
        }
        return result;
    }

    @Override
    public List<PartyFileKodFolderRespVO> getCurrentUserKodFolderTree(Long userId) {
        String rootPath = "/";
        List<PartyFileKodFolderRespVO> children = getCurrentUserKodFolderChildren(userId, rootPath);
        return Collections.singletonList(buildUserFolderNode("全部文件", rootPath,
                children, children.isEmpty()));
    }

    @Override
    public List<PartyFileKodFolderRespVO> getCurrentUserKodFolderChildren(Long userId, String kodFolderPath) {
        String path = normalizeUserFolderPath(kodFolderPath);
        JsonNode current = requestUserKodFolderList(
                kodSsoService.getCurrentUserKodAccessToken(userId), path);
        return parseUserFolderChildren(current.path("folderList"));
    }

    @Override
    public List<PartyFileKodFileRespVO> getCurrentUserKodFiles(Long userId, PartyFileKodUserFilesReqVO reqVO) {
        String path = normalizeUserFolderPath(reqVO.getKodFolderPath());
        JsonNode current = requestUserKodFolderList(kodSsoService.getCurrentUserKodAccessToken(userId), path);
        return parseKodFiles(current.path("fileList"));
    }

    @Override
    public List<PartyFileAttachmentUploadRespVO> selectCurrentUserKodFiles(Long userId,
                                                                             PartyFileKodUserSelectReqVO reqVO) {
        String accessToken = kodSsoService.getCurrentUserKodAccessToken(userId);
        String parentPath = normalizeUserFolderPath(reqVO.getKodFolderPath());
        Map<String, PartyFileKodFileRespVO> visibleFiles = new HashMap<>();
        for (PartyFileKodFileRespVO file : parseKodFiles(
                requestUserKodFolderList(accessToken, parentPath).path("fileList"))) {
            visibleFiles.put(file.getPath(), file);
        }
        List<PartyFileAttachmentUploadRespVO> result = new ArrayList<>();
        for (PartyFileKodSelectFileReqVO requested : reqVO.getFiles()) {
            PartyFileKodFileRespVO visible = visibleFiles.get(StrUtil.trim(requested.getPath()));
            if (visible == null) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        "当前用户无权选择可道云文件：" + requested.getName());
            }
            result.add(createKodAttachment(0L, parentPath, visible.getPath(), visible.getName(),
                    visible.getSize(), visible.getType()));
        }
        return result;
    }

    @Override
    public FileDO getFile(Long fileId) {
        return fileMapper.selectById(fileId);
    }

    @Override
    public byte[] getAttachmentContent(Long fileId) throws Exception {
        return getAttachmentContent(fileId,
                cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId());
    }

    @Override
    public byte[] getAttachmentContent(Long fileId, Long userId) throws Exception {
        FileDO file = fileMapper.selectById(fileId);
        if (file == null) {
            throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
        }
        PartyFileKodAttachmentDO kodAttachment = partyFileKodAttachmentMapper.selectByFileId(fileId);
        if (kodAttachment == null) {
            return fileService.getFileContent(file.getConfigId(), file.getPath());
        }
        if (Objects.equals(kodAttachment.getKodSourceId(), 0L)) {
            String accessToken = kodSsoService.getCurrentUserKodAccessToken(userId);
            return readKodFile(kodSsoService.getKodBaseUrl(), accessToken, kodAttachment.getKodFilePath(),
                    "当前用户可道云文件");
        }
        PartyFileKodSourceDO source = partyFileKodSourceService.getEnabledSource(kodAttachment.getKodSourceId());
        return partyFileKodSourceService.executeWithValidAccessToken(source, accessToken -> readKodFile(source,
                accessToken, kodAttachment.getKodFilePath()));
    }

    @Override
    public byte[] getAttachmentPreviewContent(Long fileId) throws Exception {
        return getAttachmentPreviewContent(fileId,
                cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId());
    }

    @Override
    public byte[] getAttachmentPreviewContent(Long fileId, Long userId) throws Exception {
        FileDO file = getFile(fileId);
        if (file == null) {
            throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
        }
        return filePreviewConverter.convertToPreview(file.getName(), getAttachmentContent(fileId, userId));
    }

    private PartyFileAttachmentUploadRespVO uploadLocalAttachment(MultipartFile file) throws Exception {
        byte[] content = file.getBytes();
        FileClient client = fileConfigService.getMasterFileClient();
        String path = buildLocalPath(file.getOriginalFilename());
        String url = client.upload(content, path, file.getContentType());
        FileCreateReqVO createReqVO = new FileCreateReqVO();
        createReqVO.setConfigId(client.getId());
        createReqVO.setPath(path);
        createReqVO.setName(file.getOriginalFilename());
        createReqVO.setUrl(url);
        createReqVO.setType(file.getContentType());
        createReqVO.setSize(file.getSize());
        Long fileId = fileService.createFile(createReqVO);
        return buildUploadResp(fileId, file.getOriginalFilename(), url, file.getSize(), file.getContentType());
    }

    private PartyFileAttachmentUploadRespVO uploadKodAttachment(MultipartFile file, Long kodSourceId, String kodFolderPath) throws Exception {
        if (kodSourceId == null || StrUtil.isBlank(kodFolderPath)) {
            throw exception(PARTY_FILE_STORAGE_CONFIG_INVALID);
        }
        PartyFileKodSourceDO source = partyFileKodSourceService.getEnabledSource(kodSourceId);
        String folderPath = StrUtil.trim(kodFolderPath);
        String targetPath = StrUtil.addSuffixIfNot(folderPath, "/") + buildKodFileName(file.getOriginalFilename());
        JsonNode fileInfo = partyFileKodSourceService.executeWithValidAccessToken(source,
                accessToken -> uploadKodFile(source, accessToken, folderPath, file));
        String actualFilePath = firstNonBlank(fileInfo, targetPath, "path", "pathDisplay", "downloadPath");
        if (StrUtil.isBlank(actualFilePath)) {
            actualFilePath = targetPath;
        }
        return createKodAttachment(kodSourceId, folderPath, actualFilePath, file.getOriginalFilename(),
                file.getSize(), file.getContentType());
    }

    private PartyFileAttachmentUploadRespVO buildUploadResp(Long fileId, String name, String url, Long size, String type) {
        PartyFileAttachmentUploadRespVO respVO = new PartyFileAttachmentUploadRespVO();
        respVO.setId(fileId);
        respVO.setName(name);
        respVO.setUrl(url);
        respVO.setSize(size);
        respVO.setType(type);
        return respVO;
    }

    private String buildLocalPath(String originalFilename) {
        String ext = StrUtil.subAfter(originalFilename, ".", true);
        String suffix = StrUtil.isBlank(ext) ? "" : "." + ext;
        return "party-file/" + DateUtil.today() + "/" + IdUtil.fastSimpleUUID() + suffix;
    }

    private String buildKodFileName(String originalFilename) {
        String ext = StrUtil.subAfter(originalFilename, ".", true);
        String suffix = StrUtil.isBlank(ext) ? "" : "." + ext;
        return DateUtil.formatDateTime(DateUtil.date()).replaceAll("[^0-9]", "")
                + "_" + IdUtil.fastSimpleUUID() + suffix;
    }

    private PartyFileAttachmentUploadRespVO bindKodAttachment(Long kodSourceId, String kodFolderPath,
                                                              PartyFileKodSelectFileReqVO file) {
        String fileType = StrUtil.blankToDefault(file.getType(), FileTypeUtils.getMineType(file.getName()));
        return createKodAttachment(kodSourceId, StrUtil.trim(kodFolderPath), StrUtil.trim(file.getPath()),
                file.getName(), file.getSize(), fileType);
    }

    private List<PartyFileKodFolderRespVO> parseUserFolderChildren(JsonNode folderList) {
        if (!folderList.isArray() || folderList.isEmpty()) {
            return Collections.emptyList();
        }
        List<PartyFileKodFolderRespVO> result = new ArrayList<>();
        for (JsonNode folder : folderList) {
            String childPath = firstNonBlank(folder, null, "path", "sourceID");
            String childName = firstNonBlank(folder, null, "name", "pathDisplay");
            if (StrUtil.isBlank(childPath) || StrUtil.isBlank(childName)) {
                continue;
            }
            // 不在这里继续递归。前端展开节点时再请求当前目录的直接子目录。
            result.add(buildUserFolderNode(childName, childPath, null, false));
        }
        return result;
    }

    private PartyFileKodFolderRespVO buildUserFolderNode(String name, String path,
                                                           List<PartyFileKodFolderRespVO> children,
                                                           boolean isLeaf) {
        PartyFileKodFolderRespVO node = new PartyFileKodFolderRespVO();
        node.setKey(path);
        node.setTitle(name);
        node.setValue(path);
        node.setPath(path);
        node.setIsLeaf(isLeaf);
        node.setChildren(children);
        return node;
    }

    private List<PartyFileKodFileRespVO> parseKodFiles(JsonNode fileList) {
        if (!fileList.isArray() || fileList.isEmpty()) {
            return new ArrayList<>();
        }
        List<PartyFileKodFileRespVO> result = new ArrayList<>();
        for (JsonNode fileNode : fileList) {
            PartyFileKodFileRespVO file = new PartyFileKodFileRespVO();
            file.setName(firstNonBlank(fileNode, null, "name"));
            file.setPath(firstNonBlank(fileNode, null, "path"));
            file.setPathDisplay(firstNonBlank(fileNode, null, "pathDisplay"));
            file.setSize(fileNode.has("size") ? fileNode.path("size").asLong(0L) : 0L);
            file.setType(FileTypeUtils.getMineType(file.getName()));
            if (StrUtil.isBlank(file.getName()) || StrUtil.isBlank(file.getPath())) {
                continue;
            }
            result.add(file);
        }
        return result;
    }

    private JsonNode requestUserKodFolderList(String accessToken, String path) {
        String url = kodSsoService.getKodBaseUrl()
                + "?explorer/list/path&accessToken=" + HttpUtils.encodeUtf8(accessToken)
                + "&path=" + HttpUtils.encodeUtf8(normalizeUserFolderPath(path));
        try (HttpResponse response = HttpRequest.get(url)
                .setConnectionTimeout(KOD_FOLDER_CONNECT_TIMEOUT_MILLIS)
                .setReadTimeout(KOD_FOLDER_READ_TIMEOUT_MILLIS)
                .execute()) {
            if (response.getStatus() >= 400) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        "当前用户可道云目录请求失败，HTTP " + response.getStatus());
            }
            JsonNode root = JsonUtils.parseTree(response.body());
            JsonNode data = root != null && root.has("data") && root.get("data").isObject()
                    ? root.get("data") : root;
            if (root == null || root.isMissingNode() || isKodFailure(root, data)) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        "当前用户无权访问该可道云目录或令牌已失效");
            }
            return data == null || data.isMissingNode() ? root : data;
        } catch (ServiceException ex) {
            throw ex;
        } catch (Exception ex) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                    "当前用户可道云目录请求失败：" + StrUtil.blankToDefault(ex.getMessage(), "未知错误"));
        }
    }

    private boolean isKodFailure(JsonNode root, JsonNode data) {
        if (root.has("code")) {
            JsonNode code = root.get("code");
            if (code.isBoolean()) {
                return !code.booleanValue();
            }
            return "false".equalsIgnoreCase(code.asText()) || "10001".equals(code.asText());
        }
        return data != null && data.has("code") && !"true".equalsIgnoreCase(data.get("code").asText());
    }

    private String normalizeUserFolderPath(String path) {
        String normalized = StrUtil.trim(path);
        return StrUtil.isBlank(normalized) ? "/" : normalized;
    }

    private PartyFileAttachmentUploadRespVO createKodAttachment(Long kodSourceId, String parentPath, String filePath,
                                                                String fileName, Long fileSize, String fileType) {
        FileClient client = fileConfigService.getMasterFileClient();
        String virtualUrl = "kod://" + kodSourceId + "/" + IdUtil.fastSimpleUUID();
        FileCreateReqVO createReqVO = new FileCreateReqVO();
        createReqVO.setConfigId(client.getId());
        createReqVO.setPath("kod/" + kodSourceId + "/" + IdUtil.fastSimpleUUID());
        createReqVO.setName(fileName);
        createReqVO.setUrl(virtualUrl);
        createReqVO.setType(fileType);
        createReqVO.setSize(fileSize);
        Long fileId = fileService.createFile(createReqVO);

        PartyFileKodAttachmentDO attachmentDO = new PartyFileKodAttachmentDO();
        attachmentDO.setFileId(fileId);
        attachmentDO.setKodSourceId(kodSourceId);
        attachmentDO.setKodParentPath(parentPath);
        attachmentDO.setKodFilePath(filePath);
        partyFileKodAttachmentMapper.insert(attachmentDO);
        return buildUploadResp(fileId, fileName, virtualUrl, fileSize, fileType);
    }

    private String firstNonBlank(JsonNode node, String defaultValue, String... keys) {
        if (node != null && node.isObject()) {
            for (String key : keys) {
                JsonNode value = node.get(key);
                if (value != null && !value.isNull() && StrUtil.isNotBlank(value.asText())) {
                    return value.asText();
                }
            }
        }
        return defaultValue;
    }

    private byte[] readKodFile(PartyFileKodSourceDO source, String accessToken, String filePath) {
        return readKodFile(source.getBaseUrl(), accessToken, filePath,
                partyFileKodSourceService.buildSourceLabel(source));
    }

    private byte[] readKodFile(String baseUrl, String accessToken, String filePath, String sourceLabel) {
        String url = baseUrl
                + "?explorer/index/fileOut&accessToken=" + HttpUtils.encodeUtf8(accessToken)
                + "&path=" + HttpUtils.encodeUtf8(filePath);
        try (HttpResponse response = HttpRequest.get(url).execute()) {
            if (response.getStatus() >= 400) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        "可道云文件【" + sourceLabel + "】读取失败，HTTP " + response.getStatus());
            }
            String contentType = StrUtil.blankToDefault(response.header("Content-Type"), "");
            if (StrUtil.containsIgnoreCase(contentType, "application/json")) {
                JsonNode root = JsonUtils.parseTree(response.body());
                String message = extractKodMessage(root);
                if (partyFileKodSourceService.isKodAuthFailure(message)) {
                    throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                            "可道云文件【" + sourceLabel + "】访问令牌已失效，请重新登录可道云");
                }
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        "可道云文件【" + sourceLabel + "】读取失败："
                                + StrUtil.blankToDefault(message, "读取文件失败"));
            }
            return response.bodyBytes();
        } catch (ServiceException ex) {
            throw ex;
        } catch (Exception ex) {
            throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                    "可道云文件【" + sourceLabel + "】读取失败："
                            + StrUtil.blankToDefault(ex.getMessage(), "未知错误"));
        }
    }

    private JsonNode uploadKodFile(PartyFileKodSourceDO source, String accessToken, String folderPath,
                                   MultipartFile file) throws Exception {
        String url = source.getBaseUrl() + "?explorer/upload/fileUpload"
                + "&accessToken=" + HttpUtils.encodeUtf8(accessToken)
                + "&path=" + HttpUtils.encodeUtf8(folderPath)
                + "&fileInfo=1";
        try (HttpResponse response = HttpRequest.post(url)
                .form("file", file.getBytes(), file.getOriginalFilename())
                .execute()) {
            if (response.getStatus() >= 400) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        partyFileKodSourceService.buildSourceErrorMessage(source,
                                "上传失败，HTTP " + response.getStatus()));
            }
            JsonNode root = JsonUtils.parseTree(response.body());
            if (root == null || root.isMissingNode()) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        partyFileKodSourceService.buildSourceErrorMessage(source, "上传返回为空"));
            }
            String message = extractKodMessage(root);
            if (isKodFailure(root)) {
                throw exception(PARTY_FILE_KOD_REQUEST_FAILED,
                        partyFileKodSourceService.buildSourceErrorMessage(source, message));
            }
            if (root.has("info") && root.get("info").isObject()) {
                return root.get("info");
            }
            if (root.has("data") && root.get("data").isObject()) {
                return root.get("data");
            }
            return root;
        }
    }

    private boolean isKodFailure(JsonNode root) {
        if (root == null || root.isMissingNode()) {
            return true;
        }
        if (!root.has("code")) {
            return false;
        }
        JsonNode code = root.get("code");
        if (code.isBoolean()) {
            return !code.booleanValue();
        }
        String value = code.asText();
        return Objects.equals("10001", value) || "false".equalsIgnoreCase(value);
    }

    private String extractKodMessage(JsonNode root) {
        if (root == null || root.isMissingNode()) {
            return null;
        }
        for (String key : new String[]{"data", "msg", "message", "info"}) {
            JsonNode value = root.get(key);
            if (value != null && !value.isNull() && value.isValueNode() && StrUtil.isNotBlank(value.asText())) {
                return value.asText();
            }
        }
        return null;
    }
}
