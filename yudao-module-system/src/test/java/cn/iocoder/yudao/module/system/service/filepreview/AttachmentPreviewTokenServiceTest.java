package cn.iocoder.yudao.module.system.service.filepreview;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AttachmentPreviewTokenServiceTest {

    @Test
    void createAndVerify_success() {
        AttachmentPreviewTokenService service = new AttachmentPreviewTokenService();

        String url = service.createPreviewUrl(
                AttachmentPreviewTokenService.PreviewSource.PARTY_FILE,
                11L, 22L, 33L, "实习生任务说明20260729.docx");
        String token = url.substring(url.indexOf("token=") + "token=".length());
        token = token.substring(0, token.indexOf('&'));

        assertTrue(url.contains("fullfilename=%E5%AE%9E%E4%B9%A0%E7%94%9F%E4%BB%BB%E5%8A%A1%E8%AF%B4%E6%98%8E20260729.docx"));

        AttachmentPreviewTokenService.PreviewToken result = service.verify(token);

        assertEquals(AttachmentPreviewTokenService.PreviewSource.PARTY_FILE, result.getSource());
        assertEquals(11L, result.getResourceId());
        assertEquals(22L, result.getFileId());
        assertEquals(33L, result.getUserId());
        assertNotNull(result.getExpiresAt());
    }

    @Test
    void verify_tamperedToken_failed() {
        AttachmentPreviewTokenService service = new AttachmentPreviewTokenService();
        String url = service.createPreviewUrl(
                AttachmentPreviewTokenService.PreviewSource.NOTICE,
                11L, 22L, 33L);
        String token = url.substring(url.indexOf("token=") + "token=".length());
        int signatureStart = token.indexOf('.') + 1;
        char originalSignatureChar = token.charAt(signatureStart);
        char replacementSignatureChar = originalSignatureChar == 'A' ? 'B' : 'A';
        String tamperedToken = token.substring(0, signatureStart)
                + replacementSignatureChar
                + token.substring(signatureStart + 1);

        assertThrows(RuntimeException.class, () -> service.verify(tamperedToken));
    }
}
