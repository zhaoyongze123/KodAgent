import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const orgPath = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/drag/规划院组织架构一览表.xlsx';
const accountCsvPath = '/Users/mac/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_tc376xz27m2222_cb11/temp/RWTemp/2026-06/8356ac11f3ee5f741aa545a5179604e7/20260608152558TxXJ.csv';
const outputDir = '/Users/mac/项目/若伊部署/output';
const csvPath = `${outputDir}/csv/规划院组织架构全量人员与审批流程映射表-20260710.csv`;
const xlsxPath = `${outputDir}/xlsx/规划院组织架构全量人员与审批流程映射表-20260710.xlsx`;
const previewPath = '/Users/mac/项目/若伊部署/tmp/sheets/org_full_preview.png';

const normalizeName = (value) => String(value ?? '').trim().replace(/[（(].*$/, '').trim();
const unique = (arr) => [...new Set(arr.filter(Boolean))];

const normalizeDept = (value) => {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  if (raw === '综合科-行政办公') return '综合科（行政办公）';
  if (raw === '综合科-计划经营') return '综合科（计划经营）';
  if (raw === '综合科-财务管理') return '综合科（财务管理）';
  return raw.replace(/[（(].*[）)]$/, '');
};

const roleFromPersonCell = (value) => {
  const text = String(value ?? '').trim();
  const match = text.match(/[（(](.*)[）)]/);
  return match ? match[1] : '部门成员';
};

function parseSimpleCsv(text) {
  return text.trimStart().split(/\r?\n/).map((line) => {
    const cells = [];
    let current = '';
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') { current += '"'; i += 1; }
        else quoted = !quoted;
      } else if (ch === ',' && !quoted) { cells.push(current); current = ''; }
      else current += ch;
    }
    cells.push(current);
    return cells;
  });
}

const orgWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(orgPath));
const orgSheet = orgWorkbook.worksheets.getItem('Sheet1');
const orgValues = orgSheet.getRange('A1:B69').values;

const accountWorkbook = await Workbook.fromCSV(await fs.readFile(accountCsvPath, 'utf8'), { sheetName: '账号' });
const accountValues = accountWorkbook.worksheets.getItem('账号').getRange('A1:E51').values;
const accountByName = new Map();
for (const row of accountValues.slice(1)) {
  const account = String(row[1] ?? '');
  const name = normalizeName(account.split('/')[0]);
  if (name) accountByName.set(name, { account, role: String(row[2] ?? '') });
}

const people = new Map();
const ensurePerson = (name) => {
  if (!people.has(name)) people.set(name, { name, departments: [], roles: [], memberships: [] });
  return people.get(name);
};
const addDept = (person, dept) => { if (dept && !person.departments.includes(dept)) person.departments.push(dept); };
const addRole = (person, role) => { if (role && !person.roles.includes(role)) person.roles.push(role); };
const addMembership = (person, text) => { if (text && !person.memberships.includes(text)) person.memberships.push(text); };

let currentDept = '院部';
for (let i = 0; i < orgValues.length; i += 1) {
  const rawDept = String(orgValues[i][0] ?? '').trim();
  const rawPerson = String(orgValues[i][1] ?? '').trim();
  if (rawDept) currentDept = rawDept;
  if (!rawPerson) continue;
  const name = normalizeName(rawPerson);
  if (!name) continue;
  // Excel中交通市政规划所段末的“马倩（所长）”是重复结构行；结合截图按数字城市所兼任处理。
  if (name === '马倩' && normalizeDept(currentDept) === '交通市政规划所') continue;
  const person = ensurePerson(name);
  const dept = normalizeDept(currentDept);
  if (dept !== '院部') addDept(person, dept);
  addRole(person, roleFromPersonCell(rawPerson));
  addMembership(`${dept || '院部'}：${roleFromPersonCell(rawPerson)}`);
  if (rawDept) {
    const headerLeader = normalizeName(rawDept);
    if (rawDept.includes('（') && headerLeader && headerLeader === name) addRole(person, '部门负责人/所长');
  }
}

const management = {
  '侯斌超': { roles: ['院长'], own: ['院部'], managed: [], relation: '全院最终审批节点' },
  '钱爱梅': { roles: ['分管领导（分管副院长-技术方面）'], own: ['分管领导'], managed: ['城市更新规划所', '城市设计所', '总体规划和专项规划所', '乡村规划所'], relation: '分管上述四个规划所' },
  '邴燕萍': { roles: ['分管领导（分管副院长）', '总体规划和专项规划所所长'], own: ['分管领导', '总体规划和专项规划所'], managed: [], relation: '兼任总体规划和专项规划所所长；综合科审批归张华分管' },
  '马倩': { roles: ['分管领导（分管副院长）', '城市更新规划所所长', '数字城市规划所所长'], own: ['分管领导', '城市更新规划所', '数字城市规划所'], managed: ['规划研究室', '数字城市规划所'], relation: '兼任城市更新规划所、数字城市规划所所长，并承担分管领导职责' },
  '张华': { roles: ['分管领导（总工）', '总工程师'], own: ['分管领导'], managed: ['交通市政规划所', '技术审查室', '综合科（行政办公/计划经营/财务管理）'], relation: '仅作为交通市政规划所、技术审查室、综合科三个分支的分管领导；综合科下三个分支由苏莉、何志华、翁培峰分别负责' },
  '张龄': { roles: ['总师/总规划师', '技术审查室审批节点'], own: ['总师', '技术审查室'], managed: [], relation: '技术审查室三选一节点；可直接到院长' },
  '朱新捷': { roles: ['总师/总规划师', '技术审查室审批节点'], own: ['总师', '技术审查室'], managed: [], relation: '技术审查室三选一节点；可直接到院长' },
  '苏莉': { roles: ['综合科行政办公负责人（相当于所长）'], own: ['综合科（行政办公）'], managed: ['行政办公成员'], relation: '综合科行政办公分支负责人；成员报苏莉后到张华' },
  '何志华': { roles: ['综合科计划经营负责人（相当于所长）'], own: ['综合科（计划经营）'], managed: ['计划经营成员'], relation: '综合科计划经营分支负责人；成员报何志华后到张华' },
  '翁培峰': { roles: ['综合科财务管理负责人（相当于所长）'], own: ['综合科（财务管理）'], managed: ['财务管理成员'], relation: '综合科财务管理分支负责人；成员报翁培峰后到张华' },
};
for (const [name, info] of Object.entries(management)) {
  const person = ensurePerson(name);
  for (const role of info.roles) addRole(person, role);
}

const routeFor = (person) => {
  const name = person.name;
  const depts = person.departments;
  if (name === '侯斌超') return ['院长账号无上级审批节点', 0, '保留账号，作为院长最终审批节点。'];
  if (['钱爱梅', '邴燕萍', '马倩'].includes(name)) return ['该账号属于分管领导/兼任所长，主要用于审批；作为发起人时的上级节点需单独确认', 0, '本行重点记录其多层组织归属，不将管理角色误写成普通发起流程。'];
  if (name === '张华' || name === '张龄' || name === '朱新捷') return ['侯斌超（院长）', 1, '保留账号，作为审批节点登录后人工审批。'];
  if (name === '严己') return ['张华、张龄、朱新捷三选一 → 侯斌超（院长）', 2, '验证三选一是否显示具体人名，不得自动通过。'];
  if (name === '赖志勇') return ['朱新捷（总规划师） → 侯斌超（院长）', 2, '架构图明确标注“赖志勇到朱新捷”。'];
  if (name === '李豪杰') return ['何志华（经营主管） → 张华（总工程师）', 2, '计划经营流程按“李豪杰 → 何志华 → 张华”执行。'];
  if (name === '何志华') return ['张华（总工程师/分管领导）', 1, '计划经营负责人直接向张华报批。'];
  if (name === '蒋欣怡') return ['翁培峰（财务主管） → 张华（总工程师）', 2, '财务管理成员按综合科财务分支向翁培峰报批，再到张华。'];
  if (name === '翁培峰') return ['张华（总工程师/分管领导）', 1, '财务管理负责人直接向张华报批。'];
  if (['黄华', '顾俊', '徐鑫赟'].includes(name)) return ['苏莉（办公室主任） → 张华（总工程师）', 2, '行政办公成员按“成员 → 苏莉 → 张华”执行。'];
  if (name === '苏莉') return ['张华（总工程师/分管领导）', 1, '行政办公负责人直接向张华报批。'];
  if (depts.includes('城市更新规划所')) return ['马倩（所长） → 钱爱梅（分管副院长） → 侯斌超（院长）', 3, '城市更新规划所标准流程。'];
  if (depts.includes('城市设计所')) return ['濮卫民（所长） → 钱爱梅（分管副院长） → 侯斌超（院长）', 3, '城市设计所标准流程。'];
  if (depts.includes('总体规划和专项规划所')) return ['邴燕萍（所长） → 钱爱梅（分管副院长） → 侯斌超（院长）', 3, '总体规划和专项规划所标准流程。'];
  if (depts.includes('乡村规划所')) return ['李丹（所长） → 钱爱梅（分管副院长） → 侯斌超（院长）', 3, '乡村规划所标准流程。'];
  if (depts.includes('规划研究室')) return ['罗翔（部门负责人） → 马倩（分管副院长） → 侯斌超（院长）', 3, '规划研究室标准流程。'];
  if (depts.includes('数字城市规划所')) return ['马倩（所长兼分管副院长） → 侯斌超（院长）', 2, '数字城市规划所负责人按截图标注为马倩；同一人不重复生成两个节点。'];
  if (depts.includes('交通市政规划所')) return ['缪云涛（所长） → 张华（总工程师/分管领导） → 侯斌超（院长）', 3, '交通市政规划所标准流程。'];
  if (depts.includes('综合科（行政办公）') || depts.includes('综合科（财务管理）')) return ['张华（总工程师/分管领导）', 1, '综合科分支无统一所长时，成员直接向张华报批。'];
  if (depts.includes('综合科（计划经营）')) return ['张华（总工程师/分管领导）', 1, '综合科分支无统一所长时，成员直接向张华报批。'];
  return ['未从截图确定上级审批链', 0, '已确认组织归属，但审批链需要补充确认。'];
};

const sourceRows = [...people.values()];
const rows = sourceRows.map((person, index) => {
  const account = accountByName.get(person.name) || { account: `${person.name}/${person.name}`, role: '普通用户' };
  const info = management[person.name];
  const [route, steps, routeNote] = routeFor(person);
  const role = unique([...(person.roles || []), ...(info?.roles || [])]).join('；');
  const depts = unique([...(person.departments || []), ...(info?.departments || [])]).join('；');
  const ownDepartments = unique(info?.own || person.departments);
  const managedDepartments = unique(info?.managed || []);
  const relation = info?.relation || (person.departments.includes('技术审查室') ? '技术审查室无指定所长，直接向张华（分管领导）报批' : person.departments.includes('综合科（行政办公）') ? '行政办公负责人：苏莉；成员直接向苏莉报批，再到张华' : person.departments.includes('综合科（计划经营）') ? '计划经营负责人：何志华；成员直接向何志华报批，再到张华' : person.departments.includes('综合科（财务管理）') ? '财务管理负责人：翁培峰；成员直接向翁培峰报批，再到张华' : '所属部门负责人：' + (person.departments.includes('城市更新规划所') ? '马倩' : person.departments.includes('城市设计所') ? '濮卫民' : person.departments.includes('总体规划和专项规划所') ? '邴燕萍' : person.departments.includes('乡村规划所') ? '李丹' : person.departments.includes('规划研究室') || person.departments.includes('数字城市规划所') ? '马倩' : person.departments.includes('交通市政规划所') ? '缪云涛' : person.departments.some((d) => d.startsWith('综合科')) ? '对应综合科负责人' : '见组织架构表'));
  const accountStatus = accountByName.has(person.name) ? `可道云已有账号：${account.account}；角色：${account.role}` : `原CSV未找到账号，已按规则补默认账号：${account.account}；角色：普通用户`;
  return [
    index + 1,
    person.name,
    account.account,
    account.role,
    ownDepartments.join('；'),
    managedDepartments.join('；'),
    role,
    relation,
    route,
    steps,
    accountStatus,
    routeNote,
  ];
});

const headers = ['序号', '人员', '可道云账号', '可道云角色', '本人所属/任职组织（含兼任）', '分管/管理部门', '组织角色', '分管/上下级关系', '审批经过人员（作为发起人）', '审批节点数', '账号状态/测试建议', '依据/备注'];
const csvEscape = (value) => {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n') + '\n';
await fs.mkdir(`${outputDir}/csv`, { recursive: true });
await fs.mkdir(`${outputDir}/xlsx`, { recursive: true });
await fs.writeFile(csvPath, `\uFEFF${csv}`, 'utf8');

const fullWorkbook = await Workbook.fromCSV(csv, { sheetName: '全量人员映射' });
const sheet = fullWorkbook.worksheets.getItem('全量人员映射');
const lastRow = rows.length + 1;
const used = sheet.getRange(`A1:L${lastRow}`);
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(2);
used.format.font = { name: 'PingFang SC', size: 9, color: '#1F2937' };
used.format.wrapText = true;
used.format.verticalAlignment = 'center';
used.format.borders = { preset: 'all', style: 'thin', color: '#D9E2F3' };
sheet.getRange('A1:L1').format = { fill: '#1F4E78', font: { name: 'PingFang SC', size: 10, bold: true, color: '#FFFFFF' }, horizontalAlignment: 'center', verticalAlignment: 'center', wrapText: true };
sheet.getRange(`A1:A${lastRow}`).format.columnWidth = 8;
sheet.getRange(`B1:B${lastRow}`).format.columnWidth = 14;
sheet.getRange(`C1:C${lastRow}`).format.columnWidth = 18;
sheet.getRange(`D1:D${lastRow}`).format.columnWidth = 14;
sheet.getRange(`E1:E${lastRow}`).format.columnWidth = 36;
sheet.getRange(`F1:F${lastRow}`).format.columnWidth = 34;
sheet.getRange(`G1:G${lastRow}`).format.columnWidth = 34;
sheet.getRange(`H1:H${lastRow}`).format.columnWidth = 48;
sheet.getRange(`I1:I${lastRow}`).format.columnWidth = 52;
sheet.getRange(`J1:J${lastRow}`).format.columnWidth = 12;
sheet.getRange(`K1:K${lastRow}`).format.columnWidth = 42;
sheet.getRange(`L1:L${lastRow}`).format.columnWidth = 44;
sheet.getRange('A1:L1').format.rowHeight = 30;
sheet.getRange(`A2:L${lastRow}`).format.rowHeight = 34;
sheet.getRange(`A2:L${lastRow}`).format.autofitRows();
const table = sheet.tables.add(`A1:L${lastRow}`, true, 'OrgFullPeopleMapping');
table.showFilterButton = true;
table.showBandedRows = true;
const preview = await fullWorkbook.render({ sheetName: '全量人员映射', range: 'A1:K18', scale: 1, format: 'png' });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(fullWorkbook);
await xlsx.save(xlsxPath);

console.log(`csv=${csvPath}`);
console.log(`xlsx=${xlsxPath}`);
console.log(`people=${rows.length}`);
console.log(`accounts_existing_in_source_csv=${rows.filter((row) => accountByName.has(row[1])).length}`);
console.log(`accounts_defaulted=${rows.filter((row) => !accountByName.has(row[1])).length}`);
console.log(`preview=${previewPath}`);
