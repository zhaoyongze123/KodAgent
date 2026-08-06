import { copyFileSync, globSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { basename, resolve } from 'node:path';

const rootDir = resolve(process.cwd());
const origin = (process.env.INTRANET_APP_ORIGIN || '').replace(/\/$/, '');

if (!/^https?:\/\/[^/]+$/.test(origin)) {
  throw new Error('INTRANET_APP_ORIGIN must be an http(s) origin without a path.');
}

function firstMatch(pattern) {
  const [match] = globSync(pattern, { cwd: rootDir, nodir: true });
  if (!match) {
    throw new Error(`Required offline asset not found: ${pattern}`);
  }
  return resolve(rootDir, match);
}

const vendorDir = resolve(rootDir, 'apps/web-antd/public/vendor/form-designer');
mkdirSync(vendorDir, { recursive: true });

const assets = [
  ['node_modules/.pnpm/vue@*/node_modules/vue/dist/vue.global.prod.js', 'vue.global.prod.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/dayjs.min.js', 'dayjs.min.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/customParseFormat.js', 'customParseFormat.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/weekday.js', 'weekday.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/localeData.js', 'localeData.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/weekOfYear.js', 'weekOfYear.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/weekYear.js', 'weekYear.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/advancedFormat.js', 'advancedFormat.js'],
  ['node_modules/.pnpm/dayjs@*/node_modules/dayjs/plugin/quarterOfYear.js', 'quarterOfYear.js'],
  ['node_modules/.pnpm/ant-design-vue@*/node_modules/ant-design-vue/dist/reset.css', 'reset.css'],
  ['node_modules/.pnpm/ant-design-vue@*/node_modules/ant-design-vue/dist/antd.min.js', 'antd.min.js'],
  ['node_modules/.pnpm/@form-create+ant-design-vue@*/node_modules/@form-create/ant-design-vue/dist/form-create.min.js', 'form-create.min.js'],
  ['node_modules/.pnpm/@form-create+antd-designer@*/node_modules/@form-create/antd-designer/dist/index.umd.js', 'index.umd.js'],
];

const replacements = new Map([
  ['https://unpkg.com/ant-design-vue@4/dist/reset.css', `${origin}/vendor/form-designer/reset.css`],
  ['https://unpkg.com/vue@3', `${origin}/vendor/form-designer/vue.global.prod.js`],
  ['https://unpkg.com/dayjs/dayjs.min.js', `${origin}/vendor/form-designer/dayjs.min.js`],
  ['https://unpkg.com/dayjs/plugin/customParseFormat.js', `${origin}/vendor/form-designer/customParseFormat.js`],
  ['https://unpkg.com/dayjs/plugin/weekday.js', `${origin}/vendor/form-designer/weekday.js`],
  ['https://unpkg.com/dayjs/plugin/localeData.js', `${origin}/vendor/form-designer/localeData.js`],
  ['https://unpkg.com/dayjs/plugin/weekOfYear.js', `${origin}/vendor/form-designer/weekOfYear.js`],
  ['https://unpkg.com/dayjs/plugin/weekYear.js', `${origin}/vendor/form-designer/weekYear.js`],
  ['https://unpkg.com/dayjs/plugin/advancedFormat.js', `${origin}/vendor/form-designer/advancedFormat.js`],
  ['https://unpkg.com/dayjs/plugin/quarterOfYear.js', `${origin}/vendor/form-designer/quarterOfYear.js`],
  ['https://unpkg.com/ant-design-vue@4/dist/antd.min.js', `${origin}/vendor/form-designer/antd.min.js`],
  ['https://unpkg.com/@form-create/ant-design-vue@3', `${origin}/vendor/form-designer/form-create.min.js`],
  ['https://unpkg.com/@form-create/antd-designer@3', `${origin}/vendor/form-designer/index.umd.js`],
]);

const templatePaths = [
  'node_modules/.pnpm/@form-create+antd-designer@*/node_modules/@form-create/antd-designer/src/utils/template.js',
  'node_modules/.pnpm/@form-create+antd-designer@*/node_modules/@form-create/antd-designer/dist/index.es.js',
  'node_modules/.pnpm/@form-create+antd-designer@*/node_modules/@form-create/antd-designer/dist/index.umd.js',
].map((pattern) => firstMatch(pattern));

for (const templatePath of templatePaths) {
  let template = readFileSync(templatePath, 'utf8');
  for (const [source, target] of replacements) {
    if (!template.includes(source)) {
      throw new Error(`Expected CDN reference is missing from ${basename(templatePath)}: ${source}`);
    }
    template = template.replaceAll(source, target);
  }
  writeFileSync(templatePath, template);
}

for (const [pattern, targetName] of assets) {
  copyFileSync(firstMatch(pattern), resolve(vendorDir, targetName));
}

console.log(`Patched ${templatePaths.map((path) => basename(path)).join(', ')} and copied ${assets.length} offline form-designer assets.`);
