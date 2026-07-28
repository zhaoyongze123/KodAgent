import fs from 'node:fs/promises';
import { Workbook } from '@oai/artifact-tool';

const input = '/Users/mac/项目/若伊部署/output/csv/规划院OA用户与审批流程映射表-20260710.csv';
const preview = '/Users/mac/项目/若伊部署/tmp/sheets/oa_mapping_preview.png';
const csvText = await fs.readFile(input, 'utf8');
const workbook = await Workbook.fromCSV(csvText, { sheetName: '用户流程映射' });
const inspect = await workbook.inspect({
  kind: 'table',
  range: '用户流程映射!A1:J12',
  include: 'values',
  tableMaxRows: 12,
  tableMaxCols: 10,
  maxChars: 7000,
});
console.log(inspect.ndjson);
const blob = await workbook.render({ sheetName: '用户流程映射', range: 'A1:J12', scale: 1, format: 'png' });
await fs.writeFile(preview, new Uint8Array(await blob.arrayBuffer()));
console.log(`preview=${preview}`);
