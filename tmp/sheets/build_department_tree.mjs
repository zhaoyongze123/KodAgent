import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const orgPath = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const accountCsvPath = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/RWTemp/2026-06/8356ac11f3ee5f741aa545a5179604e7/20260608152558TxXJ.csv';
const outputDir = '/Users/mac/项目/若伊部署/output';
const csvPath = `${outputDir}/csv/规划院部门树人员与审批流程-20260710.csv`;
const xlsxPath = `${outputDir}/xlsx/规划院部门树人员与审批流程-20260710.xlsx`;
const previewPath = '/Users/mac/项目/若伊部署/tmp/sheets/department_tree_preview.png';

const normalize = (value) => String(value ?? '').trim();
const normalizeName = (value) => normalize(value).replace(/[（(].*$/, '').trim();
const unique = (arr) => [...new Set(arr.filter(Boolean))];
const normalizeDept = (value) => {
  const raw = normalize(value);
  if (raw === '综合科-行政办公') return '行政办公';
  if (raw === '综合科-计划经营') return '计划经营';
  if (raw === '综合科-财务管理') return '财务管理';
  return raw.replace(/[（(].*[）)]$/, '');
};
const csvEscape = (value) => {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const orgWb = await SpreadsheetFile.importXlsx(await FileBlob.load(orgPath));
const orgValues = orgWb.worksheets.getItem('Sheet1').getRange('A1:B69').values;
const accountWb = await Workbook.fromCSV(await fs.readFile(accountCsvPath, 'utf8'), { sheetName: '账号' });
const accountValues = accountWb.worksheets.getItem('账号').getRange('A1:E51').values;
const accounts = new Map();
for (const row of accountValues.slice(1)) {
  const account = normalize(row[1]);
  const name = normalizeName(account.split('/')[0]);
  if (name) accounts.set(name, { account, role: normalize(row[2]) });
}

const deptMembers = new Map();
const deptLeaders = new Map();
let currentDept = '院部';
for (let i = 0; i < orgValues.length; i += 1) {
  const rawDept = normalize(orgValues[i][0]);
  const rawPerson = normalize(orgValues[i][1]);
  if (rawDept) currentDept = rawDept;
  if (!rawPerson || normalizeDept(currentDept) === '院部') continue;
  // Excel交通市政规划所段末的“马倩（所长）”是重复结构行，按截图归入数字城市规划所。
  if (normalizeName(rawPerson) === '马倩' && normalizeDept(currentDept) === '交通市政规划所') continue;
  const dept = normalizeDept(currentDept);
  if (!deptMembers.has(dept)) deptMembers.set(dept, []);
  const name = normalizeName(rawPerson);
  if (!deptMembers.get(dept).includes(name)) deptMembers.get(dept).push(name);
  if (rawDept.includes('（') || rawDept.includes('(')) deptLeaders.set(dept, normalizeName(rawDept));
}

const colors = {
  root: { parent: '#1F4E78', child: '#D9EAF7', person: '#F3F8FC' },
  qian: { parent: '#2F75B5', child: '#DDEBF7', person: '#F2F8FD' },
  bing: { parent: '#548235', child: '#E2F0D9', person: '#F5FAF1' },
  ma: { parent: '#C55A11', child: '#FCE4D6', person: '#FFF7F2' },
  zhang: { parent: '#7030A0', child: '#E4DFEC', person: '#FAF7FC' },
};

const rows = [];
const summaries = [];
const addRow = ({ level, path, dept, person = '', affiliation = '', route = '', note = '', colorKey = 'root', kind = 'person' }) => {
  rows.push({ level, path, dept, person, affiliation, route, note, colorKey, kind });
};

const accountText = (name) => accounts.has(name) ? accounts.get(name).account : `${name}/${name}`;
const roleText = (name) => accounts.has(name) ? accounts.get(name).role : '普通用户';
const accountNote = (name) => accounts.has(name) ? `原CSV已有账号：${accountText(name)}` : `原CSV未找到，按规则补默认账号：${accountText(name)}`;

const addPerson = ({ level, path, dept, name, affiliation, route, note = '', colorKey }) => {
  addRow({ level, path, dept, person: name, affiliation, route, note: `${accountNote(name)}；${note}`, colorKey, kind: 'person' });
};

const addDepartment = ({ path, dept, leader, members, colorKey, routeForMember, leaderNote = '' }) => {
  addRow({ level: path.split('/').length, path, dept, colorKey, kind: 'department', note: leader ? `负责人/所长：${leader}` : '未指定所长/负责人' });
  const ordered = unique([...(leader ? [leader] : []), ...members]);
  for (const name of ordered) {
    const isLeader = name === leader;
    const route = routeForMember(name, isLeader);
    addPerson({ level: path.split('/').length + 1, path, dept, name, affiliation: isLeader ? '负责人/所长' : (dept === '技术审查室' ? '部门成员/审批节点' : '部门成员'), route: route[0], note: isLeader ? leaderNote : route[1], colorKey });
  }
  summaries.push({ dept, parent: path.split('/').slice(0, -1).join('/') || '根节点', count: ordered.length, members: ordered.join('、'), route: routeForMember(ordered.find((name) => name !== leader) || leader || '', false)[0] || '见人员明细' });
};

addRow({ level: 1, path: '院部', dept: '院部', colorKey: 'root', kind: 'department', note: '院部根部门。' });
addRow({ level: 2, path: '院部/院长', dept: '院长', colorKey: 'root', kind: 'department', note: '全院最终审批节点部门。' });
addPerson({ level: 3, path: '院部/院长', dept: '院长', name: '侯斌超', affiliation: '院长/最终审批节点', route: '最终审批节点', note: '保留院长审批账号。', colorKey: 'root' });

addRow({ level: 1, path: '分管领导', dept: '分管领导', colorKey: 'root', kind: 'department', note: '按分管领导分别建立子树' });
addRow({ level: 2, path: '分管领导/钱爱梅', dept: '钱爱梅（分管副院长-技术方面）', person: '钱爱梅', affiliation: '分管领导', route: '主要作为审批节点；如作为发起人需单独确认', note: accountNote('钱爱梅'), colorKey: 'qian', kind: 'manager' });
addRow({ level: 2, path: '分管领导/邴燕萍', dept: '邴燕萍（分管副院长）', person: '邴燕萍', affiliation: '分管领导/兼任总规所所长', route: '主要作为审批节点；如作为发起人需单独确认', note: accountNote('邴燕萍'), colorKey: 'bing', kind: 'manager' });
addRow({ level: 2, path: '分管领导/马倩', dept: '马倩（分管副院长）', person: '马倩', affiliation: '分管领导/兼任两个所长', route: '主要作为审批节点；如作为发起人需单独确认', note: accountNote('马倩'), colorKey: 'ma', kind: 'manager' });
addRow({ level: 2, path: '分管领导/张华', dept: '张华（总工程师/分管领导）', person: '张华', affiliation: '分管领导/总工', route: '侯斌超（院长）', note: `${accountNote('张华')}；分管交通市政规划所、技术审查室、综合科`, colorKey: 'zhang', kind: 'manager' });

const standard = (leader, supervisor) => (name, isLeader) => [isLeader ? '作为所长/负责人保留审批账号' : `${leader}（所长） → ${supervisor}（分管领导） → 侯斌超（院长）`, '普通成员按所在所标准流程审批'];
addDepartment({ path: '分管领导/钱爱梅/城市更新规划所', dept: '城市更新规划所', leader: '马倩', members: deptMembers.get('城市更新规划所') || [], colorKey: 'qian', routeForMember: standard('马倩', '钱爱梅'), leaderNote: '马倩同时属于马倩分管领导树和本所所长节点。' });
addDepartment({ path: '分管领导/钱爱梅/城市设计所', dept: '城市设计所', leader: '濮卫民', members: deptMembers.get('城市设计所') || [], colorKey: 'qian', routeForMember: standard('濮卫民', '钱爱梅') });
addDepartment({ path: '分管领导/钱爱梅/总体规划和专项规划所', dept: '总体规划和专项规划所', leader: '邴燕萍', members: deptMembers.get('总体规划和专项规划所') || [], colorKey: 'qian', routeForMember: standard('邴燕萍', '钱爱梅'), leaderNote: '邴燕萍同时属于邴燕萍分管领导节点。' });
addDepartment({ path: '分管领导/钱爱梅/乡村规划所', dept: '乡村规划所', leader: '李丹', members: deptMembers.get('乡村规划所') || [], colorKey: 'qian', routeForMember: standard('李丹', '钱爱梅') });

addDepartment({ path: '分管领导/马倩/规划研究室', dept: '规划研究室', leader: '罗翔', members: deptMembers.get('规划研究室') || [], colorKey: 'ma', routeForMember: standard('罗翔', '马倩') });
addDepartment({ path: '分管领导/马倩/数字城市规划所', dept: '数字城市规划所', leader: '马倩', members: deptMembers.get('数字城市规划所') || [], colorKey: 'ma', routeForMember: (name, isLeader) => [isLeader ? '作为所长/分管领导保留审批账号' : '马倩（所长兼分管副院长） → 侯斌超（院长）', '数字城市规划所负责人按截图标注为马倩。'], leaderNote: '截图在数字城市规划所“所长”空白处标注为马倩。' });

addDepartment({ path: '分管领导/张华/交通市政规划所', dept: '交通市政规划所', leader: '缪云涛', members: deptMembers.get('交通市政规划所') || [], colorKey: 'zhang', routeForMember: standard('缪云涛', '张华') });

addRow({ level: 3, path: '分管领导/张华/技术审查室', dept: '技术审查室', colorKey: 'zhang', kind: 'department', note: '无指定所长；张龄、朱新捷在本部门内作为特殊审批节点。' });
const techMembers = unique(deptMembers.get('技术审查室') || ['张华', '张龄', '严己', '朱新捷', '赖志勇']);
for (const name of techMembers) {
  let route = '侯斌超（院长）';
  let affiliation = '部门成员/审批节点';
  let note = '张华、张龄、朱新捷直接到院长。';
  if (name === '严己') { route = '严己自己点选张华/张龄/朱新捷'; affiliation = '特殊节点'; note = '按截图标注“严己自己点选”。'; }
  if (name === '赖志勇') { route = '朱新捷（总规划师） → 侯斌超（院长）'; affiliation = '特殊节点'; note = '按截图标注“赖志勇到朱新捷”。'; }
  addPerson({ level: 4, path: '分管领导/张华/技术审查室', dept: '技术审查室', name, affiliation, route, note, colorKey: 'zhang' });
}

addRow({ level: 3, path: '分管领导/邴燕萍/综合科（行政/财务）', dept: '综合科（行政/财务）', person: '苏莉', affiliation: '综合科（行政/财务）所长', route: '苏莉（所长） → 邴燕萍（分管副院长） → 侯斌超（院长）', note: `${accountNote('苏莉')}；苏莉是综合科（行政/财务）大分支负责人，同时仅归属行政办公子部门。`, colorKey: 'bing', kind: 'department' });
addRow({ level: 3, path: '分管领导/张华/综合科（计划经营）', dept: '综合科（计划经营）', colorKey: 'zhang', kind: 'department', note: '计划经营独立归类，流程为李浩杰 → 何志华 → 张华。' });
summaries.push({ dept: '综合科（行政/财务）', parent: '邴燕萍', count: 6, members: '苏莉、黄华、顾俊、徐鑫赟、翁培峰、蒋欣怡', route: '行政/财务：苏莉 → 邴燕萍 → 侯斌超' });
summaries.push({ dept: '综合科（计划经营）', parent: '张华', count: 2, members: '何志华、李浩杰', route: '计划经营：李浩杰 → 何志华 → 张华' });
addDepartment({ path: '分管领导/邴燕萍/综合科（行政/财务）/行政办公', dept: '行政办公', leader: '苏莉', members: deptMembers.get('行政办公') || [], colorKey: 'bing', routeForMember: (name, isLeader) => [isLeader ? '邴燕萍（分管副院长） → 侯斌超（院长）' : '苏莉（办公室主任） → 邴燕萍（分管副院长） → 侯斌超（院长）', isLeader ? '苏莉统一负责行政办公和财务管理两条成员汇报线。' : '行政办公成员统一经过苏莉，再到邴燕萍。'], leaderNote: '苏莉负责行政办公和财务管理两部分。' });
addDepartment({ path: '分管领导/张华/综合科（计划经营）/计划经营', dept: '计划经营', leader: '何志华', members: deptMembers.get('计划经营') || [], colorKey: 'zhang', routeForMember: (name, isLeader) => [isLeader ? '张华（总工程师/分管领导）' : '何志华（经营主管） → 张华（总工程师）', isLeader ? '何志华负责计划经营分支。' : '计划经营成员经过何志华后到张华。'], leaderNote: '何志华负责综合科计划经营分支。' });
addDepartment({ path: '分管领导/邴燕萍/综合科（行政/财务）/财务管理', dept: '财务管理', leader: '', members: (deptMembers.get('财务管理') || []).filter((name) => name !== '苏莉'), colorKey: 'bing', routeForMember: (name) => ['苏莉（综合科（行政/财务）所长） → 邴燕萍（分管副院长） → 侯斌超（院长）', '财务管理不归属苏莉的行政办公部门，但财务成员审批仍经过综合科（行政/财务）所长苏莉。'], leaderNote: '财务管理不单独设置子部门所长；成员审批统一经过综合科（行政/财务）所长苏莉。' });

const headers = ['序号', '部门层级', '部门树路径', '部门/子部门', '人员', '人员归属', '审批经过人员', '可道云账号', '可道云角色', '备注'];
const csvRows = [headers, ...rows.map((row, i) => [i + 1, row.level, row.path, row.dept, row.person, row.affiliation, row.route, accountText(row.person), roleText(row.person), row.note])];
const csvText = csvRows.map((row) => row.map(csvEscape).join(',')).join('\n') + '\n';
await fs.mkdir(`${outputDir}/csv`, { recursive: true });
await fs.mkdir(`${outputDir}/xlsx`, { recursive: true });
await fs.writeFile(csvPath, `\uFEFF${csvText}`, 'utf8');

const wb = await Workbook.fromCSV(csvText, { sheetName: '部门树人员' });
const sheet = wb.worksheets.getItem('部门树人员');
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(1);
const lastRow = rows.length + 1;
const used = sheet.getRange(`A1:J${lastRow}`);
used.format.font = { name: 'PingFang SC', size: 9, color: '#1F2937' };
used.format.wrapText = true;
used.format.verticalAlignment = 'center';
used.format.borders = { preset: 'all', style: 'thin', color: '#D9E2F3' };
sheet.getRange('A1:J1').format = { fill: '#17365D', font: { name: 'PingFang SC', size: 10, bold: true, color: '#FFFFFF' }, horizontalAlignment: 'center', verticalAlignment: 'center', wrapText: true };
sheet.getRange(`A1:A${lastRow}`).format.columnWidth = 8;
sheet.getRange(`B1:B${lastRow}`).format.columnWidth = 10;
sheet.getRange(`C1:C${lastRow}`).format.columnWidth = 42;
sheet.getRange(`D1:D${lastRow}`).format.columnWidth = 28;
sheet.getRange(`E1:E${lastRow}`).format.columnWidth = 14;
sheet.getRange(`F1:F${lastRow}`).format.columnWidth = 18;
sheet.getRange(`G1:G${lastRow}`).format.columnWidth = 45;
sheet.getRange(`H1:H${lastRow}`).format.columnWidth = 18;
sheet.getRange(`I1:I${lastRow}`).format.columnWidth = 14;
sheet.getRange(`J1:J${lastRow}`).format.columnWidth = 44;
sheet.getRange('A1:J1').format.rowHeight = 30;
sheet.getRange(`A2:J${lastRow}`).format.rowHeight = 26;

for (let i = 0; i < rows.length; i += 1) {
  const rowNumber = i + 2;
  const row = rows[i];
  const fill = colors[row.colorKey][row.kind === 'department' || row.kind === 'manager' ? 'child' : 'person'];
  sheet.getRange(`A${rowNumber}:J${rowNumber}`).format.fill = fill;
  if (row.kind === 'department' || row.kind === 'manager') sheet.getRange(`A${rowNumber}:J${rowNumber}`).format.font = { name: 'PingFang SC', size: 9, bold: true, color: '#1F2937' };
  if (row.kind === 'manager') sheet.getRange(`A${rowNumber}:J${rowNumber}`).format.fill = colors[row.colorKey].parent;
}
sheet.getRange(`A2:J${lastRow}`).format.autofitRows();
const table = sheet.tables.add(`A1:J${lastRow}`, true, 'DepartmentTreePeople');
table.showFilterButton = true;
table.showBandedRows = false;

const summaryRows = [
  ['统计口径', '数量', '说明'],
  ['实际业务部门/子部门', 13, '城市更新、城市设计、总体规划和专项规划、乡村、规划研究室、数字城市、交通市政、技术审查室、综合科（行政/财务）及其行政办公/财务管理、综合科（计划经营）及其计划经营。'],
  ['一级组织节点', 2, 'OA规划院、分管领导。'],
  ['分管领导节点', 4, '钱爱梅、邴燕萍、马倩、张华，分别作为独立树分支。'],
  ['部门树节点合计（不含人员行）', 20, '1个根部门 + 1个分管领导总节点 + 1个院长部门 + 4个分管领导节点 + 13个实际业务部门/子部门。'],
  ...summaries.map((s) => ['部门成员统计', s.count, `${s.dept}｜上级：${s.parent}｜成员：${s.members}｜审批：${s.route}`]),
];
const summarySheet = wb.worksheets.add('部门统计');
summarySheet.showGridLines = false;
summarySheet.getRange(`A1:C${summaryRows.length}`).values = summaryRows;
summarySheet.getRange(`A1:C${summaryRows.length}`).format = { font: { name: 'PingFang SC', size: 10, color: '#1F2937' }, wrapText: true, verticalAlignment: 'center', borders: { preset: 'all', style: 'thin', color: '#D9E2F3' } };
summarySheet.getRange('A1:C1').format = { fill: '#17365D', font: { name: 'PingFang SC', size: 10, bold: true, color: '#FFFFFF' }, horizontalAlignment: 'center', wrapText: true };
summarySheet.getRange(`A1:A${summaryRows.length}`).format.columnWidth = 28;
summarySheet.getRange(`B1:B${summaryRows.length}`).format.columnWidth = 12;
summarySheet.getRange(`C1:C${summaryRows.length}`).format.columnWidth = 100;
summarySheet.getRange('A1:C1').format.rowHeight = 28;
summarySheet.getRange(`A2:C${summaryRows.length}`).format.rowHeight = 32;
summarySheet.getRange(`A2:C${summaryRows.length}`).format.autofitRows();
summarySheet.freezePanes.freezeRows(1);

const preview = await wb.render({ sheetName: '部门树人员', range: 'A1:J28', scale: 1, format: 'png' });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(xlsxPath);
console.log(`csv=${csvPath}`);
console.log(`xlsx=${xlsxPath}`);
console.log(`tree_rows=${rows.length}`);
console.log(`summary_departments=13`);
console.log(`preview=${previewPath}`);
