package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.server.controller.agent.AgentDocumentArtifactProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import javax.annotation.Resource;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

/** 通用附件服务：不理解业务报告类型，只渲染模型提交的文档结构。 */
@Service
public class AgentDocumentArtifactService {
    private static final String DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    private static final String XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final String WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    private static final String SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private static final int MAX_PREVIEW_ARCHIVE_BYTES = 5 * 1024 * 1024;
    private static final int MAX_PREVIEW_ENTRY_BYTES = 1024 * 1024;

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

    /**
     * 预览是下载后的另一种受控呈现，而不是第二份附件事实源。每次打开预览仍复用
     * download 的租户、用户和到期校验；只向浏览器返回由服务端解析出的只读 HTML。
     */
    public PreviewDocument preview(Long tenantId, Long userId, String artifactId) {
        ArtifactFile file = download(tenantId, userId, artifactId);
        return new PreviewDocument(file.title, file.filename, file.format,
                previewHtml(file.format, file.content, file.title));
    }

    static String previewHtml(String format, byte[] content, String title) {
        if ("DOCX".equalsIgnoreCase(format)) {
            return previewPage(title, "DOCX", docxPreview(content));
        }
        if ("XLSX".equalsIgnoreCase(format)) {
            return previewPage(title, "XLSX", xlsxPreview(content));
        }
        throw new IllegalArgumentException("该附件格式暂不支持预览");
    }

    private static Map<String, Object> metadata(String id, String title, String filename,
                                                  String format, String mime, int size) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("artifactId", id); result.put("title", title); result.put("filename", filename);
        result.put("format", format); result.put("mimeType", mime); result.put("size", size);
        return result;
    }

    private static String docxPreview(byte[] content) {
        Document document = parseXml(zipEntries(content).get("word/document.xml"));
        NodeList paragraphs = document.getElementsByTagNameNS(WORD_NS, "p");
        StringBuilder body = new StringBuilder();
        for (int i = 0; i < paragraphs.getLength(); i++) {
            Element paragraph = (Element) paragraphs.item(i);
            String text = paragraph.getTextContent();
            if (text == null || text.trim().isEmpty()) continue;
            String tag = isHeading(paragraph) ? "h2" : "p";
            body.append('<').append(tag).append('>').append(html(text.trim()))
                    .append("</").append(tag).append('>');
        }
        return body.length() == 0 ? "<p class=\"empty\">文档没有可展示的正文。</p>" : body.toString();
    }

    private static boolean isHeading(Element paragraph) {
        NodeList styles = paragraph.getElementsByTagNameNS(WORD_NS, "pStyle");
        if (styles.getLength() == 0) return false;
        String value = ((Element) styles.item(0)).getAttributeNS(WORD_NS, "val");
        return value != null && value.toLowerCase().startsWith("heading");
    }

    private static String xlsxPreview(byte[] content) {
        Map<String, byte[]> entries = zipEntries(content);
        List<String> names = workbookSheetNames(entries.get("xl/workbook.xml"));
        List<String> paths = new ArrayList<>();
        for (String path : entries.keySet()) {
            if (path.matches("xl/worksheets/sheet\\d+\\.xml")) paths.add(path);
        }
        Collections.sort(paths, Comparator.comparingInt(AgentDocumentArtifactService::sheetNumber));
        if (paths.isEmpty()) return "<p class=\"empty\">工作簿没有可展示的工作表。</p>";

        StringBuilder body = new StringBuilder();
        for (int index = 0; index < paths.size(); index++) {
            String name = index < names.size() ? names.get(index) : "工作表 " + (index + 1);
            body.append("<section class=\"sheet\"><h2>").append(html(name)).append("</h2>")
                    .append("<div class=\"table-wrap\"><table><tbody>");
            Document sheet = parseXml(entries.get(paths.get(index)));
            NodeList rows = sheet.getElementsByTagNameNS(SHEET_NS, "row");
            for (int rowIndex = 0; rowIndex < rows.getLength(); rowIndex++) {
                Element row = (Element) rows.item(rowIndex);
                NodeList cells = row.getElementsByTagNameNS(SHEET_NS, "c");
                if (cells.getLength() == 0) continue;
                body.append("<tr>");
                for (int cellIndex = 0; cellIndex < cells.getLength(); cellIndex++) {
                    body.append("<td>").append(html(cellText((Element) cells.item(cellIndex)))).append("</td>");
                }
                body.append("</tr>");
            }
            body.append("</tbody></table></div></section>");
        }
        return body.toString();
    }

    private static List<String> workbookSheetNames(byte[] content) {
        if (content == null) return Collections.emptyList();
        NodeList sheets = parseXml(content).getElementsByTagNameNS(SHEET_NS, "sheet");
        List<String> names = new ArrayList<>();
        for (int i = 0; i < sheets.getLength(); i++) {
            String name = ((Element) sheets.item(i)).getAttribute("name");
            names.add(name == null || name.trim().isEmpty() ? "工作表 " + (i + 1) : name);
        }
        return names;
    }

    private static int sheetNumber(String path) {
        String number = path.replaceAll("^.*sheet(\\d+)\\.xml$", "$1");
        try { return Integer.parseInt(number); } catch (NumberFormatException ignored) { return Integer.MAX_VALUE; }
    }

    private static String cellText(Element cell) {
        String type = cell.getAttribute("t");
        String tag = "inlineStr".equals(type) ? "t" : "v";
        NodeList values = cell.getElementsByTagNameNS(SHEET_NS, tag);
        return values.getLength() == 0 ? "" : values.item(0).getTextContent();
    }

    private static Map<String, byte[]> zipEntries(byte[] content) {
        if (content == null || content.length == 0) throw new IllegalArgumentException("附件内容为空");
        Map<String, byte[]> entries = new LinkedHashMap<>();
        int total = 0;
        try (ZipInputStream input = new ZipInputStream(new ByteArrayInputStream(content))) {
            ZipEntry entry;
            byte[] buffer = new byte[4096];
            while ((entry = input.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                int read;
                while ((read = input.read(buffer)) >= 0) {
                    total += read;
                    if (output.size() + read > MAX_PREVIEW_ENTRY_BYTES || total > MAX_PREVIEW_ARCHIVE_BYTES) {
                        throw new IllegalArgumentException("附件预览内容过大");
                    }
                    output.write(buffer, 0, read);
                }
                entries.put(entry.getName(), output.toByteArray());
            }
        } catch (IllegalArgumentException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalArgumentException("附件预览内容无效", ex);
        }
        return entries;
    }

    private static Document parseXml(byte[] content) {
        if (content == null || content.length == 0) throw new IllegalArgumentException("附件预览内容无效");
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);
            return factory.newDocumentBuilder().parse(new InputSource(
                    new StringReader(new String(content, StandardCharsets.UTF_8))));
        } catch (Exception ex) {
            throw new IllegalArgumentException("附件预览内容无效", ex);
        }
    }

    private static String previewPage(String title, String format, String content) {
        return "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<title>" + html(title) + "</title><style>"
                + "*{box-sizing:border-box}body{margin:0;background:#f8fafc;color:#172033;font:14px/1.7 -apple-system,BlinkMacSystemFont,\"Segoe UI\",\"Microsoft YaHei\",sans-serif}"
                + ".artifact-preview-document{max-width:920px;margin:0 auto;padding:32px;background:#fff;min-height:100vh}"
                + ".meta{margin:0 0 28px;color:#667085;font-size:12px}.artifact-preview-document h1{margin:0 0 4px;font-size:22px;line-height:1.4}.artifact-preview-document h2{margin:24px 0 10px;font-size:17px;line-height:1.5}.artifact-preview-document p{margin:0 0 12px;white-space:pre-wrap}.sheet{margin:0 0 30px}.table-wrap{overflow:auto;border:1px solid #e4e7ec}.table-wrap table{width:max-content;min-width:100%;border-collapse:collapse;background:#fff}.table-wrap td{padding:8px 10px;border-right:1px solid #e4e7ec;border-bottom:1px solid #e4e7ec;vertical-align:top;white-space:pre-wrap}.table-wrap tr:first-child td{background:#f2f4f7;font-weight:600}.empty{color:#667085}</style></head><body>"
                + "<article class=\"artifact-preview-document\"><h1>" + html(title)
                + "</h1><p class=\"meta\">只读预览 · " + html(format) + "</p>" + content
                + "</article></body></html>";
    }

    private static String html(String value) {
        return String.valueOf(value == null ? "" : value).replace("&", "&amp;")
                .replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;");
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

    public static final class PreviewDocument {
        public final String title, filename, format, html;
        private PreviewDocument(String title, String filename, String format, String html) {
            this.title = title;
            this.filename = filename;
            this.format = format;
            this.html = html;
        }
    }
}
