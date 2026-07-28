import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const source = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const output = '/Users/mac/项目/若伊部署/output/xlsx/规划院组织架构全量人员与审批流程映射表-20260710.xlsx';
const normalize = (v) => String(v ?? '').trim().replace(/[（(].*$/, '').trim();
const sourceWb = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const outputWb = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
const sourceValues = sourceWb.worksheets.getItem('Sheet1').getRange('A1:B69').values;
const outputValues = outputWb.worksheets.getItem('全量人员映射').getRange('A1:L67').values;
const sourceNames = new Set(sourceValues.map((row) => normalize(row[1])).filter(Boolean));
const outputNames = new Set(outputValues.slice(1).map((row) => String(row[1] ?? '').trim()).filter(Boolean));
const missing = [...sourceNames].filter((name) => !outputNames.has(name));
const find = (name) => outputValues.slice(1).find((row) => row[1] === name);
console.log(JSON.stringify({ source_unique_people: sourceNames.size, output_people: outputNames.size, missing_from_output: missing, ma_qian: find('马倩'), zhang_hua: find('张华'), zhang_ling: find('张龄') }, null, 2));
if (missing.length) process.exit(1);
