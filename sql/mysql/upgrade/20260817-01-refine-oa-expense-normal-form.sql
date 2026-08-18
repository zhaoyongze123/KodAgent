-- 补齐 OA 报销流程表单的业务字段。
-- 只影响后续发起流程和当前发布定义；历史流程实例继续按历史变量展示。
-- 执行命令必须包含 --default-character-set=utf8mb4。

SET NAMES utf8mb4;
START TRANSACTION;

SET @oa_expense_form_fields = JSON_ARRAY(
  CAST(JSON_OBJECT('type', 'select', 'field', 'type', 'title', '报销类型', '$required', TRUE,
    'props', JSON_OBJECT('placeholder', '请选择报销类型', 'allowClear', TRUE),
    'options', JSON_ARRAY(JSON_OBJECT('label', '差旅费', 'value', 1), JSON_OBJECT('label', '办公费', 'value', 2), JSON_OBJECT('label', '接待费', 'value', 3))) AS CHAR),
  CAST(JSON_OBJECT('type', 'inputNumber', 'field', 'expenseAmount', 'title', '报销金额（元）', '$required', TRUE,
    'props', JSON_OBJECT('min', 0.01, 'precision', 2, 'step', 0.01, 'placeholder', '请输入报销金额')) AS CHAR),
  CAST(JSON_OBJECT('type', 'datePicker', 'field', 'expenseDate', 'title', '费用发生日期', '$required', TRUE,
    'props', JSON_OBJECT('valueFormat', 'YYYY-MM-DD', 'format', 'YYYY-MM-DD', 'placeholder', '请选择费用发生日期')) AS CHAR),
  CAST(JSON_OBJECT('type', 'input', 'field', 'expenseDetail', 'title', '费用明细', '$required', TRUE,
    'props', JSON_OBJECT('type', 'textarea', 'rows', 4, 'placeholder', '请填写费用项目、金额构成等明细')) AS CHAR),
  CAST(JSON_OBJECT('type', 'FileUpload', 'field', 'voucherUrls', 'title', '报销凭证', '$required', TRUE,
    'props', JSON_OBJECT('multiple', TRUE, 'maxNumber', 20, 'maxSize', 20,
      'accept', JSON_ARRAY('pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'xls', 'xlsx'))) AS CHAR),
  CAST(JSON_OBJECT('type', 'input', 'field', 'reason', 'title', '报销原因/备注', '$required', TRUE,
    'props', JSON_OBJECT('type', 'textarea', 'rows', 3, 'placeholder', '请输入报销原因或备注')) AS CHAR)
);

UPDATE bpm_form
SET fields = @oa_expense_form_fields,
    remark = 'OA 报销流程表单补充金额、费用明细和凭证（20260817-01）',
    updater = '1'
WHERE name = 'OA流程表单-报销'
  AND tenant_id = 1
  AND deleted = b'0';

-- 当前发布版本读取流程定义快照，因此同步更新其字段配置。
UPDATE bpm_process_definition_info info
JOIN ACT_RE_PROCDEF definition ON definition.ID_ = info.process_definition_id
JOIN (
  SELECT KEY_, MAX(VERSION_) AS VERSION_
  FROM ACT_RE_PROCDEF
  WHERE KEY_ = 'oa_expense'
  GROUP BY KEY_
) latest ON latest.KEY_ = definition.KEY_ AND latest.VERSION_ = definition.VERSION_
SET info.form_fields = @oa_expense_form_fields,
    info.updater = '1'
WHERE info.tenant_id = 1
  AND info.deleted = b'0';

COMMIT;
