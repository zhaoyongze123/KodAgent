package cn.iocoder.yudao.module.system.controller.admin.partyfile;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.util.servlet.ServletUtils;
import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.infra.dal.dataobject.file.FileDO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileAttachmentUploadRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodFileRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodFilesReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodSelectReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodUserFilesReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileKodUserSelectReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodFolderRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileAttachmentRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFilePageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileSaveReqVO;
import cn.iocoder.yudao.module.system.enums.partyfile.PartyFileReadSourceEnum;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileAttachmentService;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletResponse;
import javax.validation.Valid;
import java.io.IOException;
import java.util.List;
import java.util.Objects;
import org.springframework.web.multipart.MultipartFile;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_ATTACHMENT_NOT_FOUND;

@Tag(name = "管理后台 - 党务文件")
@RestController
@RequestMapping("/system/party-file")
@Validated
public class PartyFileController {

    @Resource
    private PartyFileService partyFileService;
    @Resource
    private PartyFileAttachmentService partyFileAttachmentService;

    @PostMapping("/create")
    @Operation(summary = "创建党务文件")
    @PreAuthorize("@ss.hasPermission('system:party-file:create')")
    public CommonResult<Long> create(@Valid @RequestBody PartyFileSaveReqVO reqVO) {
        return success(partyFileService.createPartyFile(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改党务文件")
    @PreAuthorize("@ss.hasPermission('system:party-file:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody PartyFileSaveReqVO reqVO) {
        partyFileService.updatePartyFile(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除党务文件")
    @PreAuthorize("@ss.hasPermission('system:party-file:delete')")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        partyFileService.deletePartyFile(id);
        return success(true);
    }

    @GetMapping("/page")
    @Operation(summary = "分页查询党务文件")
    @PreAuthorize("@ss.hasPermission('system:party-file:query')")
    public CommonResult<PageResult<PartyFileRespVO>> page(@Valid PartyFilePageReqVO reqVO) {
        return success(partyFileService.getPartyFilePage(reqVO));
    }

    @GetMapping("/get")
    @Operation(summary = "获取党务文件详情")
    @PreAuthorize("@ss.hasPermission('system:party-file:query')")
    public CommonResult<PartyFileRespVO> get(@RequestParam("id") Long id) {
        return success(partyFileService.getPartyFileDetail(id));
    }

    @GetMapping("/my-page")
    @Operation(summary = "获取我的党务文件分页")
    public CommonResult<PageResult<PartyFileRespVO>> myPage(@Valid PartyFileMyPageReqVO reqVO) {
        return success(partyFileService.getMyPartyFilePage(SecurityFrameworkUtils.getLoginUserId(), reqVO));
    }

    @GetMapping("/my-get")
    @Operation(summary = "获取我的党务文件详情，并记录已读")
    public CommonResult<PartyFileRespVO> myGet(@RequestParam("id") Long id) {
        return success(partyFileService.getMyPartyFileDetail(id, SecurityFrameworkUtils.getLoginUserId(),
                SecurityFrameworkUtils.getLoginUserNickname()));
    }

    @GetMapping("/my-attachment")
    @Operation(summary = "获取我的党务文件附件信息，并记录附件预览/下载")
    public CommonResult<PartyFileRespVO> myAttachment(@RequestParam("id") Long id,
                                                      @RequestParam("fileId") Long fileId,
                                                      @Parameter(description = "附件动作，preview/download")
                                                      @RequestParam(value = "action", required = false) String action) {
        return success(partyFileService.getMyPartyFileAttachment(id, fileId,
                SecurityFrameworkUtils.getLoginUserId(), SecurityFrameworkUtils.getLoginUserNickname(),
                PartyFileReadSourceEnum.fromAction(action).getSource()));
    }

    @PostMapping("/attachment/upload")
    @Operation(summary = "上传党务文件附件")
    @PreAuthorize("@ss.hasPermission('system:party-file:update')")
    public CommonResult<PartyFileAttachmentUploadRespVO> uploadAttachment(@RequestParam("file") MultipartFile file,
                                                                          @RequestParam("storageType") Integer storageType,
                                                                          @RequestParam(value = "kodSourceId", required = false) Long kodSourceId,
                                                                          @RequestParam(value = "kodFolderPath", required = false) String kodFolderPath) throws Exception {
        return success(partyFileAttachmentService.uploadAttachment(file, storageType, kodSourceId, kodFolderPath));
    }

    @PostMapping("/attachment/kod-files")
    @Operation(summary = "获取可道云目录文件列表")
    @PreAuthorize("@ss.hasAnyPermissions('system:party-file:update', 'bpm:oa-leave:create', 'bpm:process-instance:query')")
    public CommonResult<List<PartyFileKodFileRespVO>> getKodFiles(@Valid @RequestBody PartyFileKodFilesReqVO reqVO) {
        return success(partyFileAttachmentService.getKodFiles(reqVO.getKodSourceId(), reqVO.getKodFolderPath()));
    }

    @PostMapping("/attachment/kod-select")
    @Operation(summary = "选择可道云已有文件作为党务附件")
    @PreAuthorize("@ss.hasAnyPermissions('system:party-file:update', 'bpm:oa-leave:create', 'bpm:process-instance:query')")
    public CommonResult<List<PartyFileAttachmentUploadRespVO>> selectKodFiles(@Valid @RequestBody PartyFileKodSelectReqVO reqVO) {
        return success(partyFileAttachmentService.selectKodFiles(reqVO));
    }

    @GetMapping("/attachment/kod-user-folder-tree")
    @Operation(summary = "获取当前用户有权限的可道云目录树")
    @PreAuthorize("@ss.hasAnyPermissions('bpm:oa-leave:create', 'bpm:process-instance:query', 'system:party-file:update')")
    public CommonResult<List<PartyFileKodFolderRespVO>> getCurrentUserKodFolderTree() {
        return success(partyFileAttachmentService.getCurrentUserKodFolderTree(
                SecurityFrameworkUtils.getLoginUserId()));
    }

    @GetMapping("/attachment/kod-user-folder-children")
    @Operation(summary = "按需获取当前用户有权限的可道云子目录")
    @PreAuthorize("@ss.hasAnyPermissions('bpm:oa-leave:create', 'bpm:process-instance:query', 'system:party-file:update')")
    public CommonResult<List<PartyFileKodFolderRespVO>> getCurrentUserKodFolderChildren(
            @RequestParam(value = "kodFolderPath", defaultValue = "/") String kodFolderPath) {
        return success(partyFileAttachmentService.getCurrentUserKodFolderChildren(
                SecurityFrameworkUtils.getLoginUserId(), kodFolderPath));
    }

    @PostMapping("/attachment/kod-user-files")
    @Operation(summary = "获取当前用户有权限的可道云文件")
    @PreAuthorize("@ss.hasAnyPermissions('bpm:oa-leave:create', 'bpm:process-instance:query', 'system:party-file:update')")
    public CommonResult<List<PartyFileKodFileRespVO>> getCurrentUserKodFiles(
            @Valid @RequestBody PartyFileKodUserFilesReqVO reqVO) {
        return success(partyFileAttachmentService.getCurrentUserKodFiles(
                SecurityFrameworkUtils.getLoginUserId(), reqVO));
    }

    @PostMapping("/attachment/kod-user-select")
    @Operation(summary = "按当前用户权限选择可道云附件")
    @PreAuthorize("@ss.hasAnyPermissions('bpm:oa-leave:create', 'bpm:process-instance:query', 'system:party-file:update')")
    public CommonResult<List<PartyFileAttachmentUploadRespVO>> selectCurrentUserKodFiles(
            @Valid @RequestBody PartyFileKodUserSelectReqVO reqVO) {
        return success(partyFileAttachmentService.selectCurrentUserKodFiles(
                SecurityFrameworkUtils.getLoginUserId(), reqVO));
    }

    @GetMapping("/attachment/access")
    @Operation(summary = "读取可道云附件内容")
    @PreAuthorize("@ss.hasAnyPermissions('system:party-file:query', 'bpm:oa-leave:create', 'bpm:process-instance:query')")
    public void accessAttachment(@RequestParam("fileId") Long fileId, HttpServletResponse response) throws Exception {
        FileDO file = partyFileAttachmentService.getFile(fileId);
        if (file == null) {
            throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
        }
        byte[] content = partyFileAttachmentService.getAttachmentContent(fileId);
        response.setHeader("Content-Disposition", "inline;filename=" + HttpUtils.encodeUtf8(file.getName()));
        response.setContentType(file.getType() != null ? file.getType() : "application/octet-stream");
        response.getOutputStream().write(content);
        response.getOutputStream().flush();
    }

    @GetMapping("/attachment/download")
    @Operation(summary = "下载党务文件附件")
    @PreAuthorize("@ss.hasPermission('system:party-file:query')")
    public void downloadAttachment(@RequestParam("id") Long id,
                                   @RequestParam("fileId") Long fileId,
                                   HttpServletResponse response) throws Exception {
        PartyFileRespVO detail = partyFileService.getPartyFileDetail(id);
        writePartyFileAttachment(detail, fileId, response);
    }

    @GetMapping("/my-attachment/download")
    @Operation(summary = "下载我的党务文件附件，并记录下载")
    public void downloadMyAttachment(@RequestParam("id") Long id,
                                     @RequestParam("fileId") Long fileId,
                                     HttpServletResponse response) throws Exception {
        PartyFileRespVO detail = partyFileService.getMyPartyFileAttachment(id, fileId,
                SecurityFrameworkUtils.getLoginUserId(), SecurityFrameworkUtils.getLoginUserNickname(),
                PartyFileReadSourceEnum.DOWNLOAD.getSource());
        writePartyFileAttachment(detail, fileId, response);
    }

    @GetMapping("/attachment/preview")
    @Operation(summary = "预览党务文件附件")
    @PreAuthorize("@ss.hasPermission('system:party-file:query')")
    public void previewAttachment(@RequestParam("id") Long id,
                                  @RequestParam("fileId") Long fileId,
                                  HttpServletResponse response) throws Exception {
        PartyFileRespVO detail = partyFileService.getPartyFileDetail(id);
        writePartyFileAttachmentPreview(detail, fileId, response);
    }

    @GetMapping("/my-attachment/preview")
    @Operation(summary = "预览我的党务文件附件，并记录预览")
    public void previewMyAttachment(@RequestParam("id") Long id,
                                    @RequestParam("fileId") Long fileId,
                                    HttpServletResponse response) throws Exception {
        PartyFileRespVO detail = partyFileService.getMyPartyFileAttachment(id, fileId,
                SecurityFrameworkUtils.getLoginUserId(), SecurityFrameworkUtils.getLoginUserNickname(),
                PartyFileReadSourceEnum.PREVIEW.getSource());
        writePartyFileAttachmentPreview(detail, fileId, response);
    }

    private void writePartyFileAttachment(PartyFileRespVO detail, Long fileId, HttpServletResponse response) throws Exception {
        PartyFileAttachmentRespVO attachment = detail.getAttachments().stream()
                .filter(item -> Objects.equals(item.getId(), fileId))
                .findFirst()
                .orElseThrow(() -> exception(PARTY_FILE_ATTACHMENT_NOT_FOUND));
        byte[] content = partyFileAttachmentService.getAttachmentContent(fileId);
        ServletUtils.writeAttachment(response, attachment.getName(), content);
    }

    private void writePartyFileAttachmentPreview(PartyFileRespVO detail, Long fileId, HttpServletResponse response) throws Exception {
        PartyFileAttachmentRespVO attachment = detail.getAttachments().stream()
                .filter(item -> Objects.equals(item.getId(), fileId))
                .findFirst()
                .orElseThrow(() -> exception(PARTY_FILE_ATTACHMENT_NOT_FOUND));
        byte[] content = partyFileAttachmentService.getAttachmentContent(fileId);
        writeInline(response, attachment.getName(), attachment.getType(), content);
    }

    private void writeInline(HttpServletResponse response, String filename, String contentType, byte[] content) throws IOException {
        response.setHeader("Content-Disposition", "inline;filename=" + HttpUtils.encodeUtf8(filename));
        response.setContentType(contentType != null ? contentType : "application/octet-stream");
        response.getOutputStream().write(content);
        response.getOutputStream().flush();
    }
}
