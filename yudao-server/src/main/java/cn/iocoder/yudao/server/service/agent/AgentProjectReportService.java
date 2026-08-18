package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.server.controller.agent.project.KodProjectProperties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.Resource;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.sql.ResultSet;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * 项目报告生成与受控下载服务。
 *
 * <p>DOCX 和 XLSX 从同一份确定性 ProjectAnalysisResult 生成，并且按用户保存短期
 * 二进制快照。下载时必须再次校验报告 owner，浏览器不会拿到数据库或 KodCloud 凭据。</p>
 */
@Service
public class AgentProjectReportService {

    /**
     * 项目插件桥接层统一以 Unix 时间戳传递时间；报告展示层只在这里转为北京时间。
     *
     * <p>统计、权限和任务筛选仍保留原始时间戳，避免“为了显示方便”改变业务事实。
     * DOCX/XLSX 都复用本格式，确保同一报告在不同载体中展示一致。</p>
     */
    private static final DateTimeFormatter REPORT_TIME_FORMATTER = DateTimeFormatter
            .ofPattern("yyyy-MM-dd HH:mm")
            .withZone(ZoneId.of("Asia/Shanghai"));

    @Resource private KodProjectBridgeService bridgeService;
    @Resource private AgentProjectAnalysisService analysisService;
    @Resource private AgentProjectAuditService auditService;
    @Resource private KodProjectProperties properties;
    @Resource @Qualifier("agentEventJdbcTemplate") private JdbcTemplate jdbcTemplate;

    /** 生成当前用户的 DOCX 与 XLSX 报告，并返回统一分析数据和下载标识。 */
    public Map<String, Object> create(Long tenantId, Long userId, long projectId, String reportType) {
        Map<String, Object> snapshot = bridgeService.snapshot(tenantId, userId, projectId);
        Map<String, Object> analysis = analysisService.analyze(snapshot);
        analysis.put("reportType", reportType);
        String reportId = UUID.randomUUID().toString();
        byte[] docx = docx(analysis);
        byte[] xlsx = xlsx(analysis);
        jdbcTemplate.update("INSERT INTO agent_project_report "
                        + "(report_id, tenant_id, owner_user_id, project_id, analysis_data, docx_data, xlsx_data, expires_at) "
                        + "VALUES (?, ?, ?, ?, CAST(? AS jsonb), ?, ?, CURRENT_TIMESTAMP + (? * INTERVAL '1 second'))",
                reportId, tenantId, userId, projectId, JsonUtils.toJsonString(analysis), docx, xlsx,
                properties.getReportTtlSeconds());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportId", reportId);
        result.put("projectId", projectId);
        result.put("analysis", analysis);
        result.put("exports", List.of(
                export(reportId, "docx", filename(analysis, "docx")),
                export(reportId, "xlsx", filename(analysis, "xlsx"))));
        auditService.record(tenantId, userId, projectId, "REPORT",
                numberValue(map(analysis.get("kpis")).get("asOf")),
                sourceVersions(analysis.get("documents")), reportId, null);
        return result;
    }

    /**
     * 保存主 Agent 已提交的项目叙事正文，并按用户明确的格式创建受控文件。
     *
     * <p>这是报告交付层，不参与项目统计或正文写作。DOCX 使用传入的最终正文，
     * 因而周报不会被 Java 的分析报告模板重写；若用户明确要求 XLSX，则工作簿仍由
     * Java 当前权限范围内的确定性分析快照生成。</p>
     */
    public Map<String, Object> createNarrative(Long tenantId, Long userId, long projectId,
                                                String documentType, List<String> formats, String content) {
        Map<String, Object> snapshot = bridgeService.snapshot(tenantId, userId, projectId);
        Map<String, Object> analysis = analysisService.analyze(snapshot);
        List<String> availableFormats = normalizedFormats(formats);
        analysis.put("reportType", documentType);
        analysis.put("deliveryFormats", availableFormats);
        String reportId = UUID.randomUUID().toString();
        byte[] docx = availableFormats.contains("DOCX")
                ? narrativeDocx(documentTitle(documentType), content)
                : new byte[0];
        byte[] xlsx = availableFormats.contains("XLSX") ? xlsx(analysis) : new byte[0];
        jdbcTemplate.update("INSERT INTO agent_project_report "
                        + "(report_id, tenant_id, owner_user_id, project_id, analysis_data, docx_data, xlsx_data, expires_at) "
                        + "VALUES (?, ?, ?, ?, CAST(? AS jsonb), ?, ?, CURRENT_TIMESTAMP + (? * INTERVAL '1 second'))",
                reportId, tenantId, userId, projectId, JsonUtils.toJsonString(analysis), docx, xlsx,
                properties.getReportTtlSeconds());
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reportId", reportId);
        result.put("projectId", projectId);
        result.put("analysis", analysis);
        List<Map<String, Object>> exports = new ArrayList<>();
        for (String format : availableFormats) {
            exports.add(export(reportId, format.toLowerCase(), filename(analysis, format.toLowerCase())));
        }
        result.put("exports", exports);
        auditService.record(tenantId, userId, projectId, "REPORT",
                numberValue(map(analysis.get("kpis")).get("asOf")),
                sourceVersions(analysis.get("documents")), reportId, null);
        return result;
    }

    /** 按当前用户读取尚未过期的报告文件。 */
    public ReportFile download(Long tenantId, Long userId, String reportId, String format) {
        String column = "docx".equalsIgnoreCase(format) ? "docx_data" : "xlsx".equalsIgnoreCase(format) ? "xlsx_data" : null;
        if (column == null) throw new IllegalArgumentException("报告格式不支持");
        List<ReportFile> rows = jdbcTemplate.query("SELECT project_id, analysis_data::text analysis_data, " + column + " content "
                        + "FROM agent_project_report WHERE report_id = ? AND tenant_id = ? AND owner_user_id = ? "
                        + "AND expires_at > CURRENT_TIMESTAMP",
                (ResultSet rs, int row) -> new ReportFile(
                        rs.getLong("project_id"), rs.getString("analysis_data"), null, rs.getBytes("content")),
                reportId, tenantId, userId);
        if (rows.isEmpty()) throw new IllegalArgumentException("报告不存在、已过期或无权下载");
        ReportFile result = rows.get(0);
        Map<String, Object> analysis = map(JsonUtils.parseObject(result.analysisData, Map.class));
        if (!formatAvailable(analysis, format) || result.content == null || result.content.length == 0) {
            throw new IllegalArgumentException("当前报告未生成该格式文件");
        }
        return new ReportFile(result.projectId, null,
                filename(analysis, format), result.content);
    }

    private static Map<String, Object> export(String reportId, String format, String filename) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("format", format); result.put("filename", filename); result.put("reportId", reportId);
        result.put("downloadPath", "/api/project-reports/" + reportId + "?format=" + format);
        return result;
    }

    private static String filename(Map<String, Object> analysis, String extension) {
        String name = text(map(analysis.get("project")).get("name"), "项目进度报告").replaceAll("[\\\\/:*?\"<>|]", "_");
        String reportName = documentTitle(text(analysis.get("reportType"), "PROJECT_ANALYSIS"));
        return name + "-" + reportName + "." + extension;
    }

    private static String documentTitle(String documentType) {
        if ("WEEKLY_REPORT".equals(documentType)) return "项目周报";
        if ("MONTHLY_REPORT".equals(documentType)) return "项目月报";
        if ("PROGRESS".equals(documentType) || "PROGRESS_REPORT".equals(documentType)) return "项目进度报告";
        return "项目分析报告";
    }

    private static List<String> normalizedFormats(List<String> formats) {
        List<String> result = new ArrayList<>();
        for (String raw : formats == null ? List.<String>of() : formats) {
            String format = String.valueOf(raw).trim().toUpperCase();
            if (("DOCX".equals(format) || "XLSX".equals(format)) && !result.contains(format)) result.add(format);
        }
        if (result.isEmpty()) throw new IllegalArgumentException("请至少指定一种项目文档格式");
        return result;
    }

    private static boolean formatAvailable(Map<String, Object> analysis, String format) {
        Object rawFormats = analysis.get("deliveryFormats");
        // 历史“项目分析报告”行没有 deliveryFormats，按旧的双格式契约兼容读取。
        if (!(rawFormats instanceof List)) return "docx".equalsIgnoreCase(format) || "xlsx".equalsIgnoreCase(format);
        for (Object raw : (List<?>) rawFormats) {
            if (String.valueOf(raw).equalsIgnoreCase(format)) return true;
        }
        return false;
    }

    /** 将模型最终正文转换为 DOCX 段落，章节和内容完全由本次正文决定。 */
    private static byte[] narrativeDocx(String title, String content) {
        List<String> paragraphs = new ArrayList<>();
        paragraphs.add(title);
        for (String raw : String.valueOf(content).replace('\u0000', ' ').split("\\r?\\n")) {
            String line = raw.trim();
            if (line.isEmpty()) continue;
            paragraphs.add(line);
        }
        StringBuilder body = new StringBuilder();
        for (int index = 0; index < paragraphs.size(); index++) {
            String line = paragraphs.get(index);
            String style = index == 0 ? "Title" : narrativeStyle(line);
            body.append(docxParagraph(narrativeText(line), style));
        }
        String document = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                + "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
                + body
                + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/><w:docGrid w:linePitch=\"360\"/></w:sectPr>"
                + "</w:body></w:document>";
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
                entry(zip, "[Content_Types].xml", docxContentTypes());
                entry(zip, "_rels/.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>");
                entry(zip, "word/_rels/document.xml.rels", docxDocumentRelationships());
                entry(zip, "word/document.xml", document);
                entry(zip, "word/styles.xml", docxStyles());
            }
            return bytes.toByteArray();
        } catch (Exception ex) { throw new IllegalStateException("项目正文 DOCX 生成失败", ex); }
    }

    private static String narrativeStyle(String line) {
        return line.startsWith("#") || line.matches("(?:[一二三四五六七八九十]+、|\\d+[.、]).*") ? "Heading1" : "Normal";
    }

    private static String narrativeText(String line) {
        return line.replaceFirst("^#{1,6}\\s*", "").replace("**", "").replace("__", "");
    }

    /**
     * 生成具有基础样式契约的 DOCX；内容全部来自结构化分析结果。
     *
     * <p>这里没有把 DOCX 当成 UTF-8 文本下载。DOCX 是 Office Open XML 包：除正文外
     * 还必须声明样式、文档关系和中文字体，才能让 Word、WPS、LibreOffice 与 macOS
     * 预览使用同一套字体回退。正文和样式 XML 均以 UTF-8 写入 ZIP。</p>
     */
    private static byte[] docx(Map<String, Object> analysis) {
        List<String> paragraphs = new ArrayList<>();
        Map<String, Object> project = map(analysis.get("project"));
        Map<String, Object> kpis = map(analysis.get("kpis"));
        paragraphs.add(text(project.get("name"), "项目") + "进度报告");
        paragraphs.add("生成时间：" + formatEpoch(kpis.get("asOf"), "未提供"));
        paragraphs.add("项目概览：有效任务 " + kpis.get("total") + " 项，已完成 " + kpis.get("completed")
                + " 项，逾期 " + kpis.get("overdue") + " 项，无负责人 " + kpis.get("withoutOwner") + " 项。");
        paragraphs.add("完成率：" + percentage(kpis.get("completionRate")));
        paragraphs.add("项目手工进度：" + (kpis.get("manualProgress") == null ? "未配置" : String.valueOf(kpis.get("manualProgress"))));
        paragraphs.add("项目时间范围：" + formatEpoch(kpis.get("timeFrom"), "未配置")
                + " 至 " + formatEpoch(kpis.get("timeTo"), "未配置"));
        paragraphs.add("负责人情况");
        for (Map<String, Object> member : list(analysis.get("members"))) {
            paragraphs.add(text(member.get("name"), "未指定") + "：负责 " + number(member.get("assigned"))
                    + " 项，完成 " + number(member.get("completed")) + " 项，逾期 " + number(member.get("overdue")) + " 项。");
        }
        paragraphs.add("风险事项");
        for (Map<String, Object> risk : list(analysis.get("risks"))) {
            paragraphs.add("[" + text(risk.get("severity"), "LOW") + "] " + text(risk.get("taskName"), "数据口径")
                    + "：" + text(risk.get("message"), ""));
        }
        paragraphs.add("数据缺口");
        for (Object gap : rawList(analysis.get("dataGaps"))) paragraphs.add("- " + String.valueOf(gap));
        paragraphs.add("资料引用");
        for (Map<String, Object> document : list(analysis.get("documents"))) {
            paragraphs.add(text(document.get("name"), "未命名资料") + "（文件编号 " + text(document.get("fileID"), "-") + "）");
        }
        paragraphs.add("统计口径");
        for (Object line : rawList(analysis.get("methodology"))) paragraphs.add(String.valueOf(line));
        StringBuilder body = new StringBuilder();
        for (int index = 0; index < paragraphs.size(); index++) {
            String style = index == 0 ? "Title" : docxSectionStyle(paragraphs.get(index));
            body.append(docxParagraph(paragraphs.get(index), style));
        }
        String document = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                + "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>"
                + body
                + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/><w:docGrid w:linePitch=\"360\"/></w:sectPr>"
                + "</w:body></w:document>";
        // ZipOutputStream.close 会写入 ZIP 中央目录。必须等它关闭后再取 bytes，
        // 否则下载文件虽有 PK 头，但 Word 无法定位文档条目并会报损坏或乱码。
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            entry(zip, "[Content_Types].xml", docxContentTypes());
            entry(zip, "_rels/.rels", "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>");
                entry(zip, "word/_rels/document.xml.rels", docxDocumentRelationships());
                entry(zip, "word/document.xml", document);
                entry(zip, "word/styles.xml", docxStyles());
            }
            return bytes.toByteArray();
        } catch (Exception ex) { throw new IllegalStateException("DOCX 报告生成失败", ex); }
    }

    /** 根据固定报告章节返回内置段落样式；业务内容不参与样式或 XML 结构决定。 */
    private static String docxSectionStyle(String line) {
        return "负责人情况".equals(line) || "风险事项".equals(line) || "数据缺口".equals(line)
                || "资料引用".equals(line) || "统计口径".equals(line) ? "Heading1" : "Normal";
    }

    /** 构造一个显式绑定中英文字体的段落，避免不同 Office 客户端猜测 eastAsia 字体。 */
    private static String docxParagraph(String line, String style) {
        return "<w:p><w:pPr><w:pStyle w:val=\"" + style + "\"/></w:pPr>"
                + "<w:r><w:rPr><w:rFonts w:ascii=\"Arial\" w:hAnsi=\"Arial\" w:eastAsia=\"Microsoft YaHei\" w:cs=\"Arial\"/>"
                + "<w:lang w:val=\"zh-CN\" w:eastAsia=\"zh-CN\"/></w:rPr>"
                + "<w:t xml:space=\"preserve\">" + xml(line) + "</w:t></w:r></w:p>";
    }

    /** DOCX 必需的内容类型：正文与样式都是包内的正式部件。 */
    private static String docxContentTypes() {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                + "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
                + "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                + "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
                + "<Override PartName=\"/word/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml\"/>"
                + "</Types>";
    }

    /** 将正文与样式关联，客户端不再需要为无样式文档做不确定的兼容修复。 */
    private static String docxDocumentRelationships() {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                + "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                + "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>"
                + "</Relationships>";
    }

    /**
     * 生成正文、标题和一级章节样式。
     *
     * <p>ASCII/hAnsi 使用 Arial，eastAsia 使用 Microsoft YaHei。没有雅黑的系统会
     * 按 Office 的中文字体回退显示；关键在于所有客户端都收到 eastAsia 的明确声明，
     * 不会把中文按西文字体或错误代码页解释。</p>
     */
    private static String docxStyles() {
        String fonts = "<w:rFonts w:ascii=\"Arial\" w:hAnsi=\"Arial\" w:eastAsia=\"Microsoft YaHei\" w:cs=\"Arial\"/>";
        return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                + "<w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
                + "<w:docDefaults><w:rPrDefault><w:rPr>" + fonts
                + "<w:sz w:val=\"22\"/><w:szCs w:val=\"22\"/><w:lang w:val=\"zh-CN\" w:eastAsia=\"zh-CN\"/>"
                + "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line=\"360\" w:lineRule=\"auto\"/></w:pPr></w:pPrDefault></w:docDefaults>"
                + "<w:style w:type=\"paragraph\" w:default=\"1\" w:styleId=\"Normal\"><w:name w:val=\"Normal\"/><w:qFormat/><w:rPr>"
                + fonts + "<w:sz w:val=\"22\"/><w:szCs w:val=\"22\"/></w:rPr></w:style>"
                + "<w:style w:type=\"paragraph\" w:styleId=\"Title\"><w:name w:val=\"Title\"/><w:basedOn w:val=\"Normal\"/><w:next w:val=\"Normal\"/><w:qFormat/>"
                + "<w:pPr><w:spacing w:after=\"360\"/><w:jc w:val=\"center\"/></w:pPr><w:rPr>" + fonts
                + "<w:b/><w:sz w:val=\"36\"/><w:szCs w:val=\"36\"/></w:rPr></w:style>"
                + "<w:style w:type=\"paragraph\" w:styleId=\"Heading1\"><w:name w:val=\"heading 1\"/><w:basedOn w:val=\"Normal\"/><w:next w:val=\"Normal\"/><w:qFormat/>"
                + "<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before=\"300\" w:after=\"160\"/><w:outlineLvl w:val=\"0\"/></w:pPr><w:rPr>" + fonts
                + "<w:b/><w:sz w:val=\"28\"/><w:szCs w:val=\"28\"/></w:rPr></w:style>"
                + "</w:styles>";
    }

    /** 生成五个工作表的最小 XLSX：概览、任务明细、成员负责、风险清单、数据口径。 */
    private static byte[] xlsx(Map<String, Object> analysis) {
        List<List<List<Object>>> sheets = List.of(
                List.of(List.of("项目", text(map(analysis.get("project")).get("name"), "")), List.of("有效任务", map(analysis.get("kpis")).get("total")), List.of("已完成", map(analysis.get("kpis")).get("completed")), List.of("逾期", map(analysis.get("kpis")).get("overdue")), List.of("无负责人", map(analysis.get("kpis")).get("withoutOwner")), List.of("完成率", percentage(map(analysis.get("kpis")).get("completionRate")))),
                taskRows(analysis), memberRows(analysis), riskRows(analysis), methodologyRows(analysis)
        );
        String[] names = {"概览", "任务明细", "成员负责", "风险清单", "数据口径与引用"};
        // 与 DOCX 相同，必须在 ZIP 写完中央目录后再返回完整 XLSX 二进制。
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            entry(zip, "[Content_Types].xml", contentTypes()); entry(zip, "_rels/.rels", rels());
            entry(zip, "xl/workbook.xml", workbook(names)); entry(zip, "xl/_rels/workbook.xml.rels", workbookRels());
            for (int index = 0; index < sheets.size(); index++) entry(zip, "xl/worksheets/sheet" + (index + 1) + ".xml", sheet(sheets.get(index)));
            }
            return bytes.toByteArray();
        } catch (Exception ex) { throw new IllegalStateException("Excel 报告生成失败", ex); }
    }

    private static List<List<Object>> taskRows(Map<String, Object> analysis) {
        List<List<Object>> rows = new ArrayList<>(); rows.add(row("任务编号", "任务名称", "负责人", "截止时间", "状态"));
        for (Map<String, Object> item : list(analysis.get("tasks"))) {
            // 项目任务允许没有负责人或截止时间。展示层统一转为空字符串，不能把业务空值
            // 传入 List.of，否则生成 Excel 时会因 List.of 不接受 null 而中断。
            rows.add(row(
                    text(item.get("taskID"), ""),
                    text(item.get("name"), ""),
                    text(item.get("ownerUser"), ""),
                    formatEpoch(item.get("timeTo"), ""),
                    text(map(item.get("metaInfo")).get("taskStatus"), "未设置")));
        }
        return rows;
    }
    private static List<List<Object>> memberRows(Map<String, Object> analysis) {
        List<List<Object>> rows = new ArrayList<>(); rows.add(row("负责人", "负责数", "完成数", "逾期数"));
        for (Map<String, Object> item : list(analysis.get("members"))) rows.add(row(item.get("name"), item.get("assigned"), item.get("completed"), item.get("overdue")));
        return rows;
    }
    private static List<List<Object>> riskRows(Map<String, Object> analysis) {
        List<List<Object>> rows = new ArrayList<>(); rows.add(row("级别", "类型", "任务", "说明"));
        for (Map<String, Object> item : list(analysis.get("risks"))) rows.add(row(item.get("severity"), item.get("type"), item.get("taskName"), item.get("message")));
        return rows;
    }
    private static List<List<Object>> methodologyRows(Map<String, Object> analysis) {
        List<List<Object>> rows = new ArrayList<>(); rows.add(row("统计口径与资料引用"));
        for (Object line : rawList(analysis.get("methodology"))) rows.add(row(line));
        for (Map<String, Object> document : list(analysis.get("documents"))) rows.add(row("资料：" + text(document.get("name"), "") + "（" + text(document.get("fileID"), "-") + "）"));
        return rows;
    }

    private static String contentTypes() { return "<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/worksheets/sheet2.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/worksheets/sheet3.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/worksheets/sheet4.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/><Override PartName=\"/xl/worksheets/sheet5.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/></Types>"; }
    private static String rels() { return "<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>"; }
    private static String workbook(String[] names) { StringBuilder out = new StringBuilder("<?xml version=\"1.0\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>"); for(int i=0;i<names.length;i++) out.append("<sheet name=\"").append(xml(names[i])).append("\" sheetId=\"").append(i+1).append("\" r:id=\"rId").append(i+1).append("\"/>"); return out.append("</sheets></workbook>").toString(); }
    private static String workbookRels() { StringBuilder out = new StringBuilder("<?xml version=\"1.0\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"); for(int i=1;i<=5;i++) out.append("<Relationship Id=\"rId").append(i).append("\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet").append(i).append(".xml\"/>"); return out.append("</Relationships>").toString(); }
    private static String sheet(List<List<Object>> rows) { StringBuilder out = new StringBuilder("<?xml version=\"1.0\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>"); for(int row=0;row<rows.size();row++){out.append("<row r=\"").append(row+1).append("\">"); for(int col=0;col<rows.get(row).size();col++){Object value=rows.get(row).get(col);String ref=column(col)+(row+1);if(value instanceof Number){out.append("<c r=\"").append(ref).append("\"><v>").append(value).append("</v></c>");}else{out.append("<c r=\"").append(ref).append("\" t=\"inlineStr\"><is><t xml:space=\"preserve\">").append(xml(String.valueOf(value==null?"":value))).append("</t></is></c>");}}out.append("</row>");}return out.append("</sheetData></worksheet>").toString(); }
    private static String column(int index) { StringBuilder out = new StringBuilder(); for(int n=index;n>=0;n=n/26-1) out.insert(0,(char)('A'+n%26)); return out.toString(); }
    /** XLSX 行构造器：业务数据允许缺失，展示层统一将 null 写为空白单元格。 */
    private static List<Object> row(Object... values) {
        List<Object> result = new ArrayList<>(values.length);
        for (Object value : values) result.add(value == null ? "" : value);
        return result;
    }
    private static void entry(ZipOutputStream zip, String name, String content) throws java.io.IOException { zip.putNextEntry(new ZipEntry(name)); zip.write(content.getBytes(StandardCharsets.UTF_8)); zip.closeEntry(); }
    private static String xml(String value) { return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;"); }
    @SuppressWarnings("unchecked") private static Map<String, Object> map(Object value) { return value instanceof Map ? (Map<String, Object>)value : new LinkedHashMap<>(); }
    @SuppressWarnings("unchecked") private static List<Map<String, Object>> list(Object value) { List<Map<String,Object>> out = new ArrayList<>(); if(value instanceof List) for(Object item:(List<?>)value) if(item instanceof Map) out.add((Map<String,Object>)item); return out; }
    private static List<?> rawList(Object value) { return value instanceof List ? (List<?>)value : List.of(); }
    private static String text(Object value, String fallback) { return value == null ? fallback : String.valueOf(value); }
    private static String number(Object value) { return value == null ? "0" : String.valueOf(value); }
    private static String percentage(Object value) { return value instanceof Number ? Math.round(((Number)value).doubleValue()*10000d)/100d+"%" : "未配置"; }

    /**
     * 将 KodCloud 的秒或毫秒级 Unix 时间戳安全格式化；历史字符串值则原样保留。
     *
     * @param value 原始时间字段，允许为空、数字、数字字符串或已格式化字符串
     * @param fallback 为空或无法识别时的展示文案
     * @return 统一的北京时间文本，绝不把时间戳数字直接泄露给报告读者
     */
    private static String formatEpoch(Object value, String fallback) {
        if (value == null) return fallback;
        String raw = String.valueOf(value).trim();
        if (raw.isEmpty()) return fallback;
        try {
            long epoch = Long.parseLong(raw);
            // 秒级时间戳通常为 10 位，毫秒级为 13 位；桥接层两种格式均兼容。
            if (epoch > 10_000_000_000L) epoch /= 1000L;
            // 非时间字段即使误入此方法也不显示成 1970 年，保留原值便于定位数据问题。
            if (epoch <= 946_684_800L) return raw;
            return REPORT_TIME_FORMATTER.format(Instant.ofEpochSecond(epoch));
        } catch (RuntimeException ignored) {
            return raw;
        }
    }
    private static Long numberValue(Object value) {
        if (value instanceof Number) return ((Number) value).longValue();
        try { return value == null ? null : Long.parseLong(String.valueOf(value)); }
        catch (RuntimeException ignored) { return null; }
    }
    private static List<Map<String, Object>> sourceVersions(Object raw) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> source : list(raw)) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("fileId", source.get("fileID"));
            item.put("name", source.get("name"));
            item.put("version", source.get("version"));
            item.put("contentHash", source.get("contentHash"));
            result.add(item);
        }
        return result;
    }

    /** 受控下载需要的二进制和文件名。 */
    public static final class ReportFile {
        /** 数据库中的分析 JSON 仅用于在受控下载时重建文件名，不会返回给浏览器。 */
        private final String analysisData;
        public final long projectId;
        public final String filename;
        public final byte[] content;

        private ReportFile(long projectId, String analysisData, String filename, byte[] content) {
            this.projectId = projectId;
            this.analysisData = analysisData;
            this.filename = filename;
            this.content = content;
        }
    }
}
