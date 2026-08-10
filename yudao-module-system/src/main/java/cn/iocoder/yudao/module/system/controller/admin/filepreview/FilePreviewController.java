package cn.iocoder.yudao.module.system.controller.admin.filepreview;

import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.tenant.core.aop.TenantIgnore;
import cn.iocoder.yudao.module.infra.dal.dataobject.file.FileDO;
import cn.iocoder.yudao.module.infra.service.file.FileService;
import cn.iocoder.yudao.module.system.service.filepreview.AttachmentPreviewTokenService;
import cn.iocoder.yudao.module.system.service.filepreview.FilePreviewConverter;
import cn.iocoder.yudao.module.system.service.partyfile.PartyFileAttachmentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.annotation.security.PermitAll;
import javax.servlet.http.HttpServletResponse;

import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_ATTACHMENT_NOT_FOUND;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;

/**
 * 本地预览服务读取 OA 文件的源接口。
 */
@Tag(name = "文件预览源")
@RestController
@RequestMapping("/system/file-preview")
public class FilePreviewController {

    @Resource
    private AttachmentPreviewTokenService tokenService;
    @Resource
    private FilePreviewConverter filePreviewConverter;
    @Resource
    private FileService fileService;
    @Resource
    private PartyFileAttachmentService partyFileAttachmentService;

    @GetMapping("/content")
    @PermitAll
    @TenantIgnore
    @Operation(summary = "读取短时授权的文件预览源")
    public void getContent(@RequestParam("token") @Parameter(description = "短时预览令牌") String token,
                           HttpServletResponse response) throws Exception {
        AttachmentPreviewTokenService.PreviewToken previewToken = tokenService.verify(token);
        FileDO file;
        byte[] content;
        if (previewToken.getSource() == AttachmentPreviewTokenService.PreviewSource.PARTY_FILE) {
            file = partyFileAttachmentService.getFile(previewToken.getFileId());
            if (file == null) {
                throw exception(PARTY_FILE_ATTACHMENT_NOT_FOUND);
            }
            content = partyFileAttachmentService.getAttachmentPreviewContent(
                    previewToken.getFileId(), previewToken.getUserId());
        } else {
            file = fileService.getFile(previewToken.getFileId());
            content = fileService.getFileContent(file.getConfigId(), file.getPath());
            content = filePreviewConverter.convertToPreview(file.getName(), content);
        }
        if (content == null) {
            response.setStatus(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        String filename = filePreviewConverter.getPreviewFileName(file.getName());
        response.setHeader("Content-Disposition", "inline;filename=" + HttpUtils.encodeUtf8(filename));
        response.setHeader("Cache-Control", "private, max-age=60");
        response.setContentType(filePreviewConverter.getPreviewContentType(file.getName(), file.getType()));
        response.setContentLengthLong(content.length);
        response.getOutputStream().write(content);
        response.getOutputStream().flush();
    }
}
