import fs from 'node:fs/promises';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const input = '/Users/mac/项目/若伊部署/output/csv/规划院OA用户与审批流程映射表-20260710.csv';
const outputDir = '/Users/mac/项目/若伊部署/output/xlsx';
const output = `${outputDir}/规划院OA用户与审批流程映射表-20260710.xlsx`;
const preview = '/Users/mac/项目/若伊部署/tmp/sheets/oa_mapping_xlsx_preview.png';

await fs.mkdir(outputDir, { recursive: true });
const csvText = await fs.readFile(input, 'utf8');
const workbook = await Workbook.fromCSV(csvText, { sheetName: '用户流程映射' });
const sheet = workbook.worksheets.getItem('用户流程映射');
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(2);

const used = sheet.getRange('A1:J51');
used.format.font = { name: 'PingFang SC', size: 10, color: '#1F2937' };
used.format.wrapText = true;
used.format.verticalAlignment = 'center';
used.format.borders = { preset: 'all', style: 'thin', color: '#D9E2F3' };
sheet.getRange('A1:J1').format = {
  fill: '#1F4E78',
  font: { name: 'PingFang SC', size: 10, bold: true, color: '#FFFFFF' },
  horizontalAlignment: 'center',
  verticalAlignment: 'center',
  wrapText: true,
};
sheet.getRange('A2:A51').format.horizontalAlignment = 'center';
sheet.getRange('H2:H51').format.horizontalAlignment = 'center';
sheet.getRange('A1:A51').format.columnWidth = 8;
sheet.getRange('B1:B51').format.columnWidth = 14;
sheet.getRange('C1:C51').format.columnWidth = 14;
sheet.getRange('D1:D51').format.columnWidth = 31;
sheet.getRange('E1:E51').format.columnWidth = 30;
sheet.getRange('F1:F51').format.columnWidth = 18;
sheet.getRange('G1:G51').format.columnWidth = 54;
sheet.getRange('H1:H51').format.columnWidth = 12;
sheet.getRange('I1:I51').format.columnWidth = 45;
sheet.getRange('J1:J51').format.columnWidth = 38;
sheet.getRange('A1:J1').format.rowHeight = 30;
sheet.getRange('A2:J51').format.rowHeight = 34;
sheet.getRange('A2:J51').format.autofitRows();

const table = sheet.tables.add('A1:J51', true, 'OaUserProcessTable');
table.showFilterButton = true;
table.showBandedRows = true;

const previewBlob = await workbook.render({ sheetName: '用户流程映射', range: 'A1:J16', scale: 1, format: 'png' });
await fs.writeFile(preview, new Uint8Array(await previewBlob.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(output);
console.log(`output=${output}`);
console.log(`preview=${preview}`);
