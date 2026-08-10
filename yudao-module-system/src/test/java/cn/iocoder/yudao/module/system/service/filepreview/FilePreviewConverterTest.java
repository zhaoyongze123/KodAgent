package cn.iocoder.yudao.module.system.service.filepreview;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FilePreviewConverterTest {

    private final FilePreviewConverter converter = new FilePreviewConverter();

    @Test
    void officeFormats_areConvertedToPdf() {
        assertTrue(converter.isOfficeDocument("合同.DOCX"));
        assertTrue(converter.isOfficeDocument("报销.xlsx"));
        assertTrue(converter.isOfficeDocument("汇报.ppt"));
        assertFalse(converter.isOfficeDocument("说明.pdf"));
        assertEquals("报销.pdf", converter.getPreviewFileName("报销.xlsx"));
        assertEquals("application/pdf", converter.getPreviewContentType("报销.xlsx", "application/octet-stream"));
    }
}
