package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.server.controller.agent.AgentDocumentArtifactProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/** 通用附件服务：不理解业务报告类型，只渲染模型提交的文档结构。 */
@Service
public class AgentDocumentArtifactService {
    private static final String DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private static final String XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    @Resource @Qualifier("agentEventJdbcTemplate") private JdbcTemplate jdbcTemplate;
    @Resource private AgentDocumentArtifactProperties properties;

    public Map<String, Object> create(Long tenantId, Long userId, Map<String, Object> request) {
        String title = text(request == null ? null : request.get("title"), "").trim();
        String format = text(request == null ? null : request.get("format"), "").trim().toUpperCase();
        String content = text(request == null ? null : request.get("content"), "").replace('\u0000', ' ').trim();
        if (title.isEmpty()) throw new IllegalArgumentException("附件标题不能为空");
        if (title.length() > 200) throw new IllegalArgumentException("附件标题不能超过 200 个字符");
        if (!"DOCX".equals(format) && !"XLSX".equals(format)) throw new IllegalArgumentException("附件格式只支持 DOCX 或 XLSX");
        if (content.length() > 100000) throw new IllegalArgumentException("附件正文不能超过 100000 个字符");

        byte[] bytes;
        if ("DOCX".equals(format)) {
            if (content.isEmpty()) throw new IllegalArgumentException("DOCX 正文不能为空");
            // title 只用于附件元数据和文件名。DOCX 的正文完全由模型提交，避免
            // 服务端额外插入固定标题而与模型已经写好的一级标题重复。
            bytes = docx(content);
        } else {
            bytes = xlsx(map(request == null ? null : request.get("workbook")));
        }
        String artifactId = UUID.randomUUID().toString();
        String filename = safeFilename(title) + "." + format.toLowerCase();
        String mime = "DOCX".equals(format) ? DOCX_MIME : XLSX_MIME;
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("purpose", text(request == null ? null : request.get("purpose"), "").trim());
        metadata.put("contentLength", content.length());
        jdbcTemplate.update("INSERT INTO agent_generated_artifact "
                        + "(artifact_id, tenant_id, owner_user_id, title, filename, format, mime_type, content_data, metadata, expires_at) "
                        + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS jsonb), CURRENT_TIMESTAMP + (? * INTERVAL '1 second'))",
                artifactId, tenantId, userId, title, filename, format, mime, bytes,
                JsonUtils.toJsonString(metadata), properties.getTtlSeconds());
        return metadata(artifactId, title, filename, format, mime, bytes.length);
    }

    public ArtifactFile download(Long tenantId, Long userId, String artifactId) {
        List<ArtifactFile> rows = jdbcTemplate.query("SELECT title, filename, format, mime_type, content_data "
                        + "FROM agent_generated_artifact WHERE artifact_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND expires_at > CURRENT_TIMESTAMP",
                (ResultSet rs, int row) -> new ArtifactFile(rs.getString("title"), rs.getString("filename"),
                        rs.getString("format"), rs.getString("mime_type"), rs.getBytes("content_data")),
                artifactId, tenantId, userId);
        if (rows.isEmpty() || rows.get(0).content == null || rows.get(0).content.length == 0) {
            throw new IllegalArgumentException("附件不存在、已过期或无权下载");
        }
        return rows.get(0);
    }

    private static Map<String, Object> metadata(String id, String title, String filename,
                                                  String format, String mime, int size) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("artifactId", id); result.put("title", title); result.put("filename", filename);
        result.put("format", format); result.put("mimeType", mime); result.put("size", size);
        return result;
    }

    private static byte[] docx(String content) {
        StringBuilder body = new StringBuilder();
        for (String raw : content.split("\\r?\\n")) {
            String line = raw.trim();
            if (line.isEmpty()) continue;
            String style = line.matches("^#{1,6}\\s+.*") || line.matches("^(?:[一二三四五六七八九十]+、|\\d+[.、]).*") ? "Heading1" : "Normal";
            body.append(paragraph(line.replaceFirst("^#{1,6}\\s*", "").replace("**", ""), style));
        }
        String document = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                + "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
                + body + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\"/></w:sectPr></w:body></w:document>";
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
                entry(zip, "[Content_Types].xml", "<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>");
                entry(zip, "_rels/.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>");
                entry(zip, "word/document.xml", document);
            }
            return bytes.toByteArray();
        } catch (Exception ex) { throw new IllegalStateException("DOCX 附件生成失败", ex); }
    }

    private static byte[] xlsx(Map<String, Object> workbook) {
        Object rawSheets = workbook.get("sheets");
        if (!(rawSheets instanceof List) || ((List<?>) rawSheets).isEmpty()) throw new IllegalArgumentException("XLSX 至少需要一个工作表");
        List<Map<String, Object>> sheets = new ArrayList<>();
        for (Object raw : (List<?>) rawSheets) if (raw instanceof Map) sheets.add(map(raw));
        if (sheets.isEmpty() || sheets.size() > 20) throw new IllegalArgumentException("工作表数量无效");
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
                entry(zip, "[Content_Types].xml", xlsxTypes(sheets.size()));
                entry(zip, "_rels/.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>");
                StringBuilder workbookXml = new StringBuilder("<?xml version=\"1.0\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>");
                StringBuilder rels = new StringBuilder("<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">");
                for (int i = 0; i < sheets.size(); i++) {
                    String name = safeSheetName(text(sheets.get(i).get("name"), "Sheet" + (i + 1)), i);
                    workbookXml.append("<sheet name=\"").append(xml(name)).append("\" sheetId=\"").append(i + 1).append("\" r:id=\"rId").append(i + 1).append("\"/>");
                    rels.append("<Relationship Id=\"rId").append(i + 1).append("\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet").append(i + 1).append(".xml\"/>");
                    entry(zip, "xl/worksheets/sheet" + (i + 1) + ".xml", sheet(sheets.get(i).get("rows")));
                }
                entry(zip, "xl/workbook.xml", workbookXml.append("</sheets></workbook>").toString());
                entry(zip, "xl/_rels/workbook.xml.rels", rels.append("</Relationships>").toString());
            }
            return bytes.toByteArray();
        } catch (Exception ex) { throw new IllegalStateException("XLSX 附件生成失败", ex); }
    }

    private static String sheet(Object rawRows) {
        StringBuilder out = new StringBuilder("<?xml version=\"1.0\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>");
        if (rawRows instanceof List) {
            int rowNo = 0;
            for (Object rawRow : (List<?>) rawRows) {
                if (!(rawRow instanceof List)) continue;
                rowNo++; out.append("<row r=\"").append(rowNo).append("\">"); int col = 0;
                for (Object value : (List<?>) rawRow) {
                    String ref = column(col++) + rowNo;
                    if (value instanceof Number || value instanceof Boolean) out.append("<c r=\"").append(ref).append("\"><v>").append(xml(String.valueOf(value))).append("</v></c>");
                    else out.append("<c r=\"").append(ref).append("\" t=\"inlineStr\"><is><t xml:space=\"preserve\">").append(xml(text(value, ""))).append("</t></is></c>");
                }
                out.append("</row>");
            }
        }
        return out.append("</sheetData></worksheet>").toString();
    }

    private static String paragraph(String value, String style) {
        return "<w:p><w:pPr><w:pStyle w:val=\"" + style + "\"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii=\"Arial\" w:hAnsi=\"Arial\" w:eastAsia=\"Microsoft YaHei\"/></w:rPr><w:t xml:space=\"preserve\">" + xml(value) + "</w:t></w:r></w:p>";
    }
    private static String xlsxTypes(int count) { StringBuilder out = new StringBuilder("<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"); for (int i=1;i<=count;i++) out.append("<Override PartName=\"/xl/worksheets/sheet").append(i).append(".xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"); return out.append("</Types>").toString(); }
    private static String column(int index) { StringBuilder out = new StringBuilder(); for (int n=index; n>=0; n=n/26-1) out.insert(0, (char)('A' + n%26)); return out.toString(); }
    private static String safeFilename(String value) { return value.replaceAll("[\\\\/:*?\"<>|]", "_").replaceAll("\\s+", " ").trim(); }
    private static String safeSheetName(String value, int index) { String name = value.replaceAll("[\\\\/?*\\[\\]:]", "_").trim(); return (name.isEmpty() ? "Sheet" + (index + 1) : name).substring(0, Math.min(31, name.isEmpty() ? 6 : name.length())); }
    private static String xml(String value) { return String.valueOf(value == null ? "" : value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;"); }
    private static String text(Object value, String fallback) { return value == null ? fallback : String.valueOf(value); }
    @SuppressWarnings("unchecked") private static Map<String, Object> map(Object value) { return value instanceof Map ? (Map<String, Object>) value : new LinkedHashMap<>(); }
    private static void entry(ZipOutputStream zip, String name, String content) throws Exception { zip.putNextEntry(new ZipEntry(name)); zip.write(content.getBytes(StandardCharsets.UTF_8)); zip.closeEntry(); }

    public static final class ArtifactFile {
        public final String title, filename, format, mimeType;
        public final byte[] content;
        private ArtifactFile(String title, String filename, String format, String mimeType, byte[] content) { this.title = title; this.filename = filename; this.format = format; this.mimeType = mimeType; this.content = content; }
    }
}
