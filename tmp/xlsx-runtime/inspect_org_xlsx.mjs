import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const path = '/Users/mac/项目/若伊部署/output/xlsx/规划院部门树人员与审批流程-20260710.xlsx';
const input = await FileBlob.load(path);
const wb = await SpreadsheetFile.importXlsx(input);
console.log((await wb.inspect({kind:'sheet', include:'id,name'})).ndjson);
console.log((await wb.inspect({kind:'workbook,sheet,table', maxChars:12000, tableMaxRows:12, tableMaxCols:12, tableMaxCellChars:100})).ndjson);
for (const name of ['部门树人员','部门统计']) {
  const sheet = wb.worksheets.getItem(name);
  const used = sheet.getUsedRange();
  console.log(`--- ${name} used ---`);
  console.log(used ? JSON.stringify(used.values) : 'null');
}
