package cn.iocoder.yudao.module.system.service.filepreview;

import cn.hutool.core.io.IoUtil;
import cn.hutool.core.util.StrUtil;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.PARTY_FILE_PREVIEW_CONVERT_FAILED;

/**
 * 将需要转换的 Office 附件统一转换成 PDF，交给本地预览服务处理。
 */
@Component
@Slf4j
public class FilePreviewConverter {

    private static final long CONVERT_TIMEOUT_SECONDS = 60L;

    @Value("${yudao.party-file.preview.libreoffice-path:soffice}")
    private String libreOfficePath = "soffice";

    public byte[] convertToPreview(String fileName, byte[] content) throws Exception {
        if (content == null || !isOfficeDocument(fileName)) {
            return content;
        }
        return convertOfficeDocumentToPdf(fileName, content);
    }

    public boolean isOfficeDocument(String fileName) {
        String lowerName = StrUtil.blankToDefault(fileName, "").toLowerCase(Locale.ROOT);
        return lowerName.endsWith(".doc") || lowerName.endsWith(".docx")
                || lowerName.endsWith(".xls") || lowerName.endsWith(".xlsx")
                || lowerName.endsWith(".ppt") || lowerName.endsWith(".pptx")
                || lowerName.endsWith(".odt") || lowerName.endsWith(".ods")
                || lowerName.endsWith(".odp") || lowerName.endsWith(".rtf");
    }

    public String getPreviewFileName(String fileName) {
        if (!isOfficeDocument(fileName)) {
            return StrUtil.blankToDefault(fileName, "preview");
        }
        String name = StrUtil.blankToDefault(fileName, "document.docx");
        int index = name.lastIndexOf('.');
        return (index > 0 ? name.substring(0, index) : name) + ".pdf";
    }

    public String getPreviewContentType(String fileName, String originalContentType) {
        return isOfficeDocument(fileName) ? "application/pdf"
                : StrUtil.blankToDefault(originalContentType, "application/octet-stream");
    }

    private byte[] convertOfficeDocumentToPdf(String fileName, byte[] content) throws Exception {
        Path workDir = Files.createTempDirectory("oa-file-preview-");
        String safeName = StrUtil.blankToDefault(fileName, "document.docx")
                .replaceAll("[^a-zA-Z0-9._-]", "_");
        Path source = workDir.resolve(safeName);
        Path output = workDir.resolve(stripExtension(safeName) + ".pdf");
        try {
            Files.write(source, content);
            Process process = new ProcessBuilder(
                    libreOfficePath,
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", workDir.toString(),
                    source.toString())
                    .redirectErrorStream(true)
                    .start();
            boolean completed = process.waitFor(CONVERT_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                throw exception(PARTY_FILE_PREVIEW_CONVERT_FAILED, "LibreOffice 转换超时");
            }
            String outputText = new String(IoUtil.readBytes(process.getInputStream()), StandardCharsets.UTF_8);
            if (process.exitValue() != 0 || !Files.exists(output)) {
                throw exception(PARTY_FILE_PREVIEW_CONVERT_FAILED,
                        StrUtil.blankToDefault(outputText, "LibreOffice 转换进程失败"));
            }
            return Files.readAllBytes(output);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw exception(PARTY_FILE_PREVIEW_CONVERT_FAILED, "LibreOffice 转换被中断");
        } catch (IOException e) {
            log.error("[convertOfficeDocumentToPdf][文件({}) 转换失败]", fileName, e);
            throw exception(PARTY_FILE_PREVIEW_CONVERT_FAILED, e.getMessage());
        } finally {
            deletePreviewDirectory(workDir);
        }
    }

    private String stripExtension(String fileName) {
        int index = fileName.lastIndexOf('.');
        return index > 0 ? fileName.substring(0, index) : fileName;
    }

    private void deletePreviewDirectory(Path workDir) {
        if (workDir == null) {
            return;
        }
        try (Stream<Path> paths = Files.walk(workDir)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException e) {
                    log.warn("[deletePreviewDirectory][临时文件({}) 删除失败]", path, e);
                }
            });
        } catch (IOException e) {
            log.warn("[deletePreviewDirectory][临时目录({}) 清理失败]", workDir, e);
        }
    }
}
