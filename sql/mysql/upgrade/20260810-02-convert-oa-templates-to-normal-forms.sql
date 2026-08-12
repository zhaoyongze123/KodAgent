-- 将当前 11 个 OA 审批模板从“业务表单”迁移为“流程表单”。
--
-- 新发起的流程仅保存 Flowable 流程实例及变量，不再写入 bpm_oa_* 业务表；
-- 旧流程定义与旧业务数据不改动，仍可按原业务表单查看。
-- 本脚本只更新每个流程当前已发布的最高版本，且可重复执行。
-- 执行命令必须包含 --default-character-set=utf8mb4，避免中文字段配置被写成乱码。

SET NAMES utf8mb4;
START TRANSACTION;

SET @oa_form_conf = JSON_OBJECT(
  'form', JSON_OBJECT(
    'layout', 'horizontal',
    'labelAlign', 'right',
    'size', 'middle',
    'colon', FALSE,
    'labelCol', JSON_OBJECT('style', JSON_OBJECT('width', '125px')),
    'wrapperCol', JSON_OBJECT('span', 24),
    'labelWidth', '100px'
  ),
  'resetBtn', JSON_OBJECT('show', FALSE, 'innerText', '重置'),
  'submitBtn', JSON_OBJECT('show', TRUE, 'innerText', '提交'),
  'col', JSON_OBJECT(
    'span', 12,
    'xs', 24,
    'sm', 24,
    'md', 12,
    'lg', 12,
    'xl', 12
  ),
  'row', JSON_OBJECT('gutter', 16),
  'formName', ''
);

CREATE TEMPORARY TABLE tmp_oa_normal_forms (
  process_key VARCHAR(64) NOT NULL,
  form_name VARCHAR(64) NOT NULL,
  conf LONGTEXT NOT NULL,
  fields LONGTEXT NOT NULL,
  PRIMARY KEY (process_key),
  UNIQUE KEY uk_form_name (form_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- bpm_form.fields 的格式是“JSON 字符串数组”，不能直接存 JSON 对象数组。
INSERT INTO tmp_oa_normal_forms (process_key, form_name, conf, fields) VALUES
(
  'oa_attendance', 'OA流程表单-补卡', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '补卡类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择补卡类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '上班漏打卡', 'value', 1), JSON_OBJECT('label', '下班漏打卡', 'value', 2), JSON_OBJECT('label', '外勤补卡', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '补卡原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入补卡原因')) AS CHAR)
  )
),
(
  'oa_trip', 'OA流程表单-出差', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '出差类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择出差类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '项目调研', 'value', 1), JSON_OBJECT('label', '汇报对接', 'value', 2), JSON_OBJECT('label', '外地驻场', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '出差原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入出差原因')) AS CHAR)
  )
),
(
  'oa_expense', 'OA流程表单-报销', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '报销类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择报销类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '差旅费', 'value', 1), JSON_OBJECT('label', '办公费', 'value', 2), JSON_OBJECT('label', '接待费', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '报销原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入报销原因')) AS CHAR)
  )
),
(
  'oa_leave', 'OA流程表单-请假', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'DictSelect', 'field', 'type', 'title', '请假类型', '$required', TRUE, 'modelField', 'value', 'props', JSON_OBJECT('dictType', 'bpm_oa_leave_type', 'valueType', 'int', 'selectType', 'select', 'placeholder', '请选择请假类型', 'allowClear', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入原因')) AS CHAR)
  )
),
(
  'oa_leave_cancel', 'OA流程表单-销假', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'DictSelect', 'field', 'type', 'title', '销假类型', '$required', TRUE, 'modelField', 'value', 'props', JSON_OBJECT('dictType', 'bpm_oa_leave_type', 'valueType', 'int', 'selectType', 'select', 'placeholder', '请选择销假类型', 'allowClear', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '销假原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入销假原因')) AS CHAR)
  )
),
(
  'oa_overtime', 'OA流程表单-加班', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '加班类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择加班类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '工作日加班', 'value', 1), JSON_OBJECT('label', '周末加班', 'value', 2), JSON_OBJECT('label', '节假日加班', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'workDate', 'title', '加班日期', '$required', TRUE, 'props', JSON_OBJECT('valueFormat', 'YYYY-MM-DD', 'format', 'YYYY-MM-DD', 'placeholder', '请选择加班日期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'durationHours', 'title', '加班时长（小时）', '$required', TRUE, 'props', JSON_OBJECT('min', 0.5, 'step', 0.5, 'precision', 2, 'placeholder', '请输入加班时长')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'workLocation', 'title', '加班地点', 'props', JSON_OBJECT('placeholder', '请输入加班地点')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectName', 'title', '关联项目', 'props', JSON_OBJECT('placeholder', '请输入关联项目')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'compensationType', 'title', '补偿方式', 'props', JSON_OBJECT('placeholder', '请选择补偿方式', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '调休', 'value', 1), JSON_OBJECT('label', '加班费', 'value', 2), JSON_OBJECT('label', '无', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'workContent', 'title', '加班内容', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入加班内容')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '申请说明', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入申请说明')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
),
(
  'oa_outing', 'OA流程表单-临时外出', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '临时外出类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择临时外出类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '项目现场', 'value', 1), JSON_OBJECT('label', '政府汇报', 'value', 2), JSON_OBJECT('label', '商务洽谈', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'outingDate', 'title', '外出日期', '$required', TRUE, 'props', JSON_OBJECT('valueFormat', 'YYYY-MM-DD', 'format', 'YYYY-MM-DD', 'placeholder', '请选择外出日期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'endTime', 'title', '结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'durationHours', 'title', '外出时长（小时）', '$required', TRUE, 'props', JSON_OBJECT('min', 0.5, 'step', 0.5, 'precision', 2, 'placeholder', '请输入外出时长')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'destination', 'title', '外出地点', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入外出地点')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'outsideOffice', 'title', '外出范围', 'props', JSON_OBJECT('placeholder', '请选择外出范围', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '院内外出', 'value', FALSE), JSON_OBJECT('label', '离院外出', 'value', TRUE))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'contactMobile', 'title', '联系电话', 'props', JSON_OBJECT('placeholder', '请输入联系电话')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'companionNames', 'title', '同行人员', 'props', JSON_OBJECT('placeholder', '请输入同行人员，多个用顿号分隔')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '临时外出原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入临时外出原因')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
),
(
  'oa_seal', 'OA流程表单-用章申请', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '用章类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择用章类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '公章', 'value', 1), JSON_OBJECT('label', '合同章', 'value', 2), JSON_OBJECT('label', '财务章', 'value', 3))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'fileName', 'title', '文件名称', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入文件名称')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'fileCount', 'title', '文件份数', '$required', TRUE, 'props', JSON_OBJECT('min', 1, 'precision', 0, 'placeholder', '请输入文件份数')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '用章事由', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入用章事由')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'startTime', 'title', '使用时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择使用时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'counterpartUnit', 'title', '对方单位', 'props', JSON_OBJECT('placeholder', '请输入对方单位')) AS CHAR),
    CAST(JSON_OBJECT('type', 'switch', 'field', 'externalCarry', 'title', '是否外带') AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'operatorName', 'title', '经办人', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入经办人')) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentUrls', 'title', '附件', 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
),
(
  'oa_document', 'OA流程表单-合同文件审批', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'fileType', 'title', '文件类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择文件类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '合同', 'value', '合同'), JSON_OBJECT('label', '函件', 'value', '函件'), JSON_OBJECT('label', '请示', 'value', '请示'), JSON_OBJECT('label', '公文', 'value', '公文'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'title', 'title', '文件标题', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入文件标题')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'relatedProject', 'title', '关联项目', 'props', JSON_OBJECT('placeholder', '请输入关联项目')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'counterpartUnit', 'title', '对方单位', 'props', JSON_OBJECT('placeholder', '请输入对方单位')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'amount', 'title', '金额', 'props', JSON_OBJECT('min', 0, 'precision', 2, 'placeholder', '请输入金额')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '审批事由', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入审批事由')) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentBodyUrls', 'title', '附件正文', 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentExtraUrls', 'title', '附件补充材料', 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
),
(
  'oa_project', 'OA流程表单-项目立项申请', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectName', 'title', '项目名称', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入项目名称')) AS CHAR),
    CAST(JSON_OBJECT('type', 'select', 'field', 'projectType', 'title', '项目类型', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择项目类型', 'allowClear', TRUE), 'options', JSON_ARRAY(JSON_OBJECT('label', '总体规划', 'value', '总体规划'), JSON_OBJECT('label', '详细规划', 'value', '详细规划'), JSON_OBJECT('label', '专项规划', 'value', '专项规划'), JSON_OBJECT('label', '城市设计', 'value', '城市设计'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'ownerUnit', 'title', '业主单位', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入业主单位')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectSource', 'title', '项目来源', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入项目来源')) AS CHAR),
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'projectLeaderId', 'title', '项目负责人', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请选择项目负责人')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectOverview', 'title', '项目概况', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入项目概况')) AS CHAR),
    CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'projectAmount', 'title', '合同金额/预估金额', '$required', TRUE, 'props', JSON_OBJECT('min', 0, 'precision', 2, 'placeholder', '请输入金额')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'plannedStartTime', 'title', '计划开始时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择计划开始时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'plannedEndTime', 'title', '计划结束时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择计划结束时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'participantDeptIds', 'title', '参与部门', 'props', JSON_OBJECT('multiple', TRUE, 'returnType', 'id', 'placeholder', '请选择参与部门')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'riskDescription', 'title', '风险说明', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入风险说明')) AS CHAR),
    CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'attachmentUrls', 'title', '附件', 'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 10, 'maxSize', 20, 'accept', JSON_ARRAY('doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'pdf', 'png', 'jpg', 'jpeg'))) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
),
(
  'oa_staffing', 'OA流程表单-项目人员调配申请', @oa_form_conf,
  JSON_ARRAY(
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'applicantUserId', 'title', '申请人', 'props', JSON_OBJECT('defaultCurrentUser', TRUE, 'disabled', TRUE)) AS CHAR),
    CAST(JSON_OBJECT('type', 'DeptSelect', 'field', 'applicantDeptId', 'title', '部门', 'props', JSON_OBJECT('defaultCurrentDept', TRUE, 'disabled', TRUE, 'returnType', 'id')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'projectName', 'title', '所属项目', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入所属项目')) AS CHAR),
    CAST(JSON_OBJECT('type', 'UserSelect', 'field', 'memberIds', 'title', '调入/调出人员', '$required', TRUE, 'props', JSON_OBJECT('multiple', TRUE, 'placeholder', '请选择调入/调出人员')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '调配原因', '$required', TRUE, 'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请输入调配原因')) AS CHAR),
    CAST(JSON_OBJECT('type', 'datePicker', 'field', 'transferTime', 'title', '调配时间', '$required', TRUE, 'props', JSON_OBJECT('showTime', TRUE, 'valueFormat', 'x', 'format', 'YYYY-MM-DD HH:mm:ss', 'placeholder', '请选择调配时间')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'expectedWorkPeriod', 'title', '预计工作周期', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入预计工作周期')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'targetUnit', 'title', '接收部门或项目组', '$required', TRUE, 'props', JSON_OBJECT('placeholder', '请输入接收部门或项目组')) AS CHAR),
    CAST(JSON_OBJECT('type', 'input', 'field', 'remark', 'title', '备注', 'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入备注')) AS CHAR)
  )
);

-- 每个名称在租户 1 下只创建一次，已有记录不重复插入。
INSERT INTO bpm_form (name, status, conf, fields, remark, creator, updater, tenant_id)
SELECT form_name, 0, conf, fields, 'OA 业务表单转流程表单（20260810-02）', '1', '1', 1
FROM tmp_oa_normal_forms source
WHERE NOT EXISTS (
  SELECT 1
  FROM bpm_form target
  WHERE target.name = source.form_name
    AND target.tenant_id = 1
    AND target.deleted = b'0'
);

-- 允许脚本因网络中断后安全重跑，并将已创建的同名迁移表单校正为本次定义。
UPDATE bpm_form form
JOIN tmp_oa_normal_forms source ON source.form_name = form.name
SET form.status = 0,
    form.conf = source.conf,
    form.fields = source.fields,
    form.remark = 'OA 业务表单转流程表单（20260810-02）',
    form.updater = '1'
WHERE form.tenant_id = 1
  AND form.deleted = b'0';

-- 流程模型：NORMAL(10) 表示流程表单；移除业务表单专用前端路径。
UPDATE ACT_RE_MODEL model
JOIN tmp_oa_normal_forms source ON source.process_key = model.KEY_
JOIN bpm_form form ON form.name = source.form_name
  AND form.tenant_id = 1
  AND form.deleted = b'0'
SET model.META_INFO_ = JSON_REMOVE(
  JSON_SET(
    model.META_INFO_,
    '$.formType', 10,
    '$.formId', form.id
  ),
  '$.formCustomCreatePath',
  '$.formCustomViewPath'
);

-- 已发布流程定义：仅更新当前最高版本，避免历史流程详情的表单契约被改变。
UPDATE bpm_process_definition_info info
JOIN ACT_RE_PROCDEF definition ON definition.ID_ = info.process_definition_id
JOIN (
  SELECT process_key, MAX(version_no) AS max_version_no
  FROM (
    SELECT KEY_ AS process_key, VERSION_ AS version_no
    FROM ACT_RE_PROCDEF
    WHERE KEY_ LIKE 'oa_%'
  ) latest_candidates
  GROUP BY process_key
) latest ON latest.process_key = definition.KEY_
  AND latest.max_version_no = definition.VERSION_
JOIN tmp_oa_normal_forms source ON source.process_key = definition.KEY_
JOIN bpm_form form ON form.name = source.form_name
  AND form.tenant_id = 1
  AND form.deleted = b'0'
SET info.form_type = 10,
    info.form_id = form.id,
    info.form_conf = form.conf,
    info.form_fields = form.fields,
    info.form_custom_create_path = NULL,
    info.form_custom_view_path = NULL,
    info.updater = '1'
WHERE info.deleted = b'0'
  AND info.tenant_id = 1;

-- 隐藏直达旧业务表单的菜单，统一从 OA 工作台进入流程表单。
-- 不删除旧路由、权限或业务数据，历史记录仍可保留和排查。
UPDATE system_menu
SET visible = b'0',
    updater = '1'
WHERE deleted = b'0'
  AND component LIKE 'bpm/oa/%';

DROP TEMPORARY TABLE tmp_oa_normal_forms;

COMMIT;
