-- 完善 OA 流程表单字段与两列排版。
-- 仅影响后续发起流程和各流程当前发布版本的表单快照；历史实例保持原变量与原表单契约。
-- 执行命令必须包含 --default-character-set=utf8mb4。

SET NAMES utf8mb4;
START TRANSACTION;

CREATE TEMPORARY TABLE tmp_oa_form_refinements (
  process_key VARCHAR(64) NOT NULL,
  form_name VARCHAR(64) NOT NULL,
  fields LONGTEXT NOT NULL,
  remark VARCHAR(255) NOT NULL,
  PRIMARY KEY (process_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 两列表单中：短字段默认半列；开始/结束时间连续排列；文本、附件与多人选择占整行。
INSERT INTO tmp_oa_form_refinements (process_key, form_name, fields, remark) VALUES
(
  'oa_attendance', 'OA流程表单-补卡',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '补卡类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择补卡类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '上班漏打卡', 'value', 1), JSON_OBJECT('label', '下班漏打卡', 'value', 2), JSON_OBJECT('label', '外勤补卡', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'attendanceDate', 'title', '补卡日期', '$required', TRUE, 'props', JSON_OBJECT('valueFormat', 'YYYY-MM-DD', 'format', 'YYYY-MM-DD', 'placeholder', '请选择补卡日期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'missingPunchTime', 'title', '应打卡时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择应打卡时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '补卡原因', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入补卡原因')) AS CHAR)
  ),
  'OA 流程表单补卡字段与布局完善（20260817-02）'
),
(
  'oa_trip', 'OA流程表单-出差',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '出差类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择出差类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '项目调研', 'value', 1), JSON_OBJECT('label', '汇报对接', 'value', 2), JSON_OBJECT('label', '外地驻场', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'destination', 'title', '出差地点', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入出差地点')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'transport', 'title', '交通方式', 'props', JSON_OBJECT('placeholder', '请选择交通方式', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '公务用车', 'value', '公务用车'), JSON_OBJECT('label', '公共交通', 'value', '公共交通'), JSON_OBJECT('label', '自驾', 'value', '自驾'), JSON_OBJECT('label', '其他', 'value', '其他'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '出差事由', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入出差事由')) AS CHAR)
  ),
  'OA 流程表单出差字段与布局完善（20260817-02）'
),
(
  'oa_leave_cancel', 'OA流程表单-销假',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'DictSelect', 'field', 'type', 'title', '销假类型', '$required', TRUE, 'modelField', 'value', 'props', JSON_OBJECT('dictType', 'bpm_oa_leave_type', 'valueType', 'int', 'selectType', 'select', 'placeholder', '请选择销假类型', 'allowClear', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'originalLeaveNo', 'title', '原请假单号', 'props', JSON_OBJECT('placeholder', '请输入原请假单号（如有）')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '原请假开始时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择原请假开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '实际返岗时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择实际返岗时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '销假说明', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入销假说明')) AS CHAR)
  ),
  'OA 流程表单销假字段与布局完善（20260817-02）'
),
(
  'oa_outing', 'OA流程表单-临时外出',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '临时外出类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择临时外出类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '项目现场', 'value', 1), JSON_OBJECT('label', '政府汇报', 'value', 2), JSON_OBJECT('label', '商务洽谈', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'outingDate', 'title', '外出日期', '$required', TRUE, 'props', JSON_OBJECT('valueFormat', 'YYYY-MM-DD', 'format', 'YYYY-MM-DD', 'placeholder', '请选择外出日期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'durationHours', 'title', '外出时长（小时）', '$required', TRUE, 'props', JSON_OBJECT('min', 0.5, 'step', 0.5, 'precision', 2, 'placeholder', '请输入外出时长')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'destination', 'title', '外出地点', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入外出地点')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'outsideOffice', 'title', '外出范围', 'props', JSON_OBJECT('placeholder', '请选择外出范围', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '院内外出', 'value', FALSE), JSON_OBJECT('label', '离院外出', 'value', TRUE))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'contactMobile', 'title', '联系电话', 'props', JSON_OBJECT('placeholder', '请输入联系电话')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'companionNames', 'title', '同行人员', 'props', JSON_OBJECT('placeholder', '请输入同行人员，多个用顿号分隔')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '临时外出原因', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入临时外出原因')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  ),
  'OA 流程表单临时外出布局完善（20260817-02）'
),
(
  'oa_document', 'OA流程表单-合同文件审批',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'fileType', 'title', '文件类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择文件类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '合同', 'value', '合同'), JSON_OBJECT('label', '函件', 'value', '函件'), JSON_OBJECT('label', '请示', 'value', '请示'), JSON_OBJECT('label', '公文', 'value', '公文'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'title', 'title', '文件标题', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入文件标题')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'relatedProject', 'title', '关联项目', 'props', JSON_OBJECT('placeholder', '请输入关联项目')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'counterpartUnit', 'title', '对方单位', 'props', JSON_OBJECT('placeholder', '请输入对方单位')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'amount', 'title', '金额（元）', 'props', JSON_OBJECT('min', 0, 'precision', 2, 'placeholder', '请输入金额')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '审批事由', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入审批事由')) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentBodyUrls', 'title', '附件正文', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentExtraUrls', 'title', '附件补充材料', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  ),
  'OA 流程表单合同文件字段与布局完善（20260817-02）'
),
(
  'oa_project', 'OA流程表单-项目立项申请',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectName', 'title', '项目名称', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入项目名称')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'projectType', 'title', '项目类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择项目类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '总体规划', 'value', '总体规划'), JSON_OBJECT('label', '详细规划', 'value', '详细规划'), JSON_OBJECT('label', '专项规划', 'value', '专项规划'), JSON_OBJECT('label', '城市设计', 'value', '城市设计'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'ownerUnit', 'title', '业主单位', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入业主单位')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectSource', 'title', '项目来源', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入项目来源')) AS CHAR),
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'projectLeaderId', 'title', '项目负责人', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择项目负责人')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'projectAmount', 'title', '合同金额/预估金额（元）', '$required', TRUE, 'props', JSON_OBJECT('min', 0.01, 'precision', 2, 'step', 0.01, 'placeholder', '请输入金额')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'plannedStartTime', 'title', '计划开始时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择计划开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'plannedEndTime', 'title', '计划结束时间', '$required', TRUE, 'col', JSON_OBJECT('span', 12, 'xs', 24, 'sm', 24, 'md', 12, 'lg', 12, 'xl', 12), 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择计划结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'participantDeptIds', 'title', '参与部门', 'props', JSON_OBJECT('multiple', TRUE, 'returnType', 'id', 'placeholder', '请选择参与部门')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectOverview', 'title', '项目概况', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入项目概况')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'riskDescription', 'title', '风险说明', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入风险说明')) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentUrls', 'title', '附件', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  ),
  'OA 流程表单项目立项字段与布局完善（20260817-02）'
),
(
  'oa_staffing', 'OA流程表单-项目人员调配申请',
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectName', 'title', '所属项目', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入所属项目')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'transferDirection', 'title', '调配类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择调配类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '调入', 'value', '调入'), JSON_OBJECT('label', '调出', 'value', '调出'), JSON_OBJECT('label', '借调', 'value', '借调'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'memberIds', 'title', '调配人员', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('multiple', TRUE, 'placeholder', '请选择调配人员')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'transferTime', 'title', '调配时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择调配时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'expectedWorkPeriod', 'title', '预计工作周期', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入预计工作周期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'targetUnit', 'title', '接收部门或项目组', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入接收部门或项目组')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '调配原因', '$required', TRUE, 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入调配原因')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'col', JSON_OBJECT('span', 24, 'xs', 24, 'sm', 24, 'md', 24, 'lg', 24, 'xl', 24), 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  ),
  'OA 流程表单人员调配字段与布局完善（20260817-02）'
);

UPDATE bpm_form form
JOIN tmp_oa_form_refinements source ON source.form_name = form.name
SET form.fields = source.fields,
    form.remark = source.remark,
    form.updater = '1'
WHERE form.tenant_id = 1
  AND form.deleted = b'0';

-- 当前流程定义有一份表单快照，必须与 bpm_form 同步；历史定义与实例不改。
UPDATE bpm_process_definition_info info
JOIN ACT_RE_PROCDEF definition ON definition.ID_ = info.process_definition_id
JOIN (
  SELECT KEY_, MAX(VERSION_) AS VERSION_
  FROM ACT_RE_PROCDEF
  WHERE KEY_ IN (
    'oa_attendance', 'oa_trip', 'oa_leave_cancel', 'oa_outing',
    'oa_document', 'oa_project', 'oa_staffing'
  )
  GROUP BY KEY_
) latest ON latest.KEY_ = definition.KEY_ AND latest.VERSION_ = definition.VERSION_
JOIN tmp_oa_form_refinements source ON source.process_key = definition.KEY_
SET info.form_fields = source.fields,
    info.updater = '1'
WHERE info.tenant_id = 1
  AND info.deleted = b'0';

DROP TEMPORARY TABLE tmp_oa_form_refinements;

COMMIT;
