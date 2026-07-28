import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const input = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const sheet = wb.worksheets.getItem('Sheet1');
const values = sheet.getRange('A1:B69').values;
values.forEach((row, i) => console.log(`${i + 1}\t${row[0] ?? ''}\t${row[1] ?? ''}`));
