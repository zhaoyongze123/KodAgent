import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const source = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const output = '/Users/mac/项目/若伊部署/output/xlsx/规划院部门树人员与审批流程-20260710.xlsx';
const normalize = (v) => String(v ?? '').trim().replace(/[（(].*$/, '').trim();
const sourceWb = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
const treeWb = await SpreadsheetFile.importXlsx(await FileBlob.load(output));
const sourceRows = sourceWb.worksheets.getItem('Sheet1').getRange('A1:B69').values;
const treeRows = treeWb.worksheets.getItem('部门树人员').getRange('A1:J88').values;
const sourceNames = new Set(sourceRows.map((row) => normalize(row[1])).filter(Boolean));
const treeNames = new Set(treeRows.slice(1).map((row) => String(row[4] ?? '').trim()).filter(Boolean));
const missing = [...sourceNames].filter((name) => !treeNames.has(name));
console.log(JSON.stringify({ source_unique_people: sourceNames.size, tree_unique_people: treeNames.size, missing_from_tree: missing, tree_rows: treeRows.length - 1 }, null, 2));
if (missing.length) process.exit(1);
