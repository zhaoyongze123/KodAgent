import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const input = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const file = await FileBlob.load(input);
const workbook = await SpreadsheetFile.importXlsx(file);
console.log((await workbook.inspect({ kind: 'sheet', include: 'id,name', maxChars: 2000 })).ndjson);
console.log((await workbook.inspect({ kind: 'workbook,sheet,table,region', maxChars: 12000, tableMaxRows: 80, tableMaxCols: 12, tableMaxCellChars: 120 })).ndjson);
for (const sheet of workbook.worksheets.items) {
  const preview = await workbook.render({ sheetName: sheet.name, autoCrop: 'all', scale: 1, format: 'png' });
  const bytes = new Uint8Array(await preview.arrayBuffer());
  const b64 = Buffer.from(bytes).toString('base64');
  console.log(`IMAGE_BASE64 ${sheet.name} ${b64}`);
}
