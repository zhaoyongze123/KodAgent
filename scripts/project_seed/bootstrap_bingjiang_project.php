<?php
/**
 * 滨江片区城市更新与综合交通提升规划的数据基线初始化。
 *
 * 这是本地 KodCloud 试点的部署脚本，不属于 Agent 运行链路：
 * - 项目、任务、活动日志和资料文件仍写入 KodCloud 的原生 SQLite 事实源；
 * - PostgreSQL 只会在后续 Java 同步时接收可失效的检索副本；
 * - 默认只预览，必须传 --apply 才会修改运行中的 KodCloud 数据。
 *
 * 用法（容器内）：
 *   php /tmp/bootstrap_bingjiang_project.php --source=/tmp/bingjiang-documents --apply
 */

declare(strict_types=1);

date_default_timezone_set('Asia/Shanghai');

$apply = in_array('--apply', $argv, true);
$force = in_array('--force', $argv, true);
$sourceArgument = null;
foreach ($argv as $argument) {
    if (strpos($argument, '--source=') === 0) $sourceArgument = substr($argument, strlen('--source='));
}
if (!$sourceArgument || !is_dir($sourceArgument)) {
    fwrite(STDERR, "缺少有效 --source=<生成资料目录> 参数\n");
    exit(2);
}

$kodRoot = getenv('KOD_ROOT') ?: '/var/www/html';
$dataRoot = $kodRoot . '/data';
if (!defined('USER_SYSTEM')) define('USER_SYSTEM', $dataRoot . '/system/');
$config = array();
include $kodRoot . '/config/setting_user.php';
$databasePath = $config['database']['DB_NAME'] ?? '';
if (!$databasePath || !is_file($databasePath)) {
    fwrite(STDERR, "无法定位 KodCloud SQLite 数据库\n");
    exit(2);
}

$database = new PDO('sqlite:' . $databasePath, null, null, array(PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION));
$project = $database->query("SELECT projectID, name FROM plugin_project WHERE name='滨江片区城市更新与综合交通提升规划' AND status=1")
    ->fetch(PDO::FETCH_ASSOC);
if (!$project) {
    fwrite(STDERR, "未找到目标项目“滨江片区城市更新与综合交通提升规划”\n");
    exit(2);
}
$projectId = (int) $project['projectID'];

function unix_time(string $value): int {
    $time = strtotime($value . ' Asia/Shanghai');
    if ($time === false) throw new RuntimeException('无效时间：' . $value);
    return $time;
}

function file_extension(string $name): string {
    $position = strrpos($name, '.');
    return $position === false ? '' : strtolower(substr($name, $position + 1));
}

function storage_path(string $dataRoot, string $virtualPath): string {
    if (strpos($virtualPath, '{io:1}/') !== 0) throw new RuntimeException('不支持的 KodCloud 文件路径：' . $virtualPath);
    return $dataRoot . '/files/' . substr($virtualPath, strlen('{io:1}/'));
}

function content_hash(string $content): array {
    $md5 = md5($content);
    return array($md5, $md5 . strlen($content));
}

function upsert_meta(PDO $database, string $table, string $idField, int $id, string $key, string $value, int $now): void {
    $select = $database->prepare("SELECT id FROM {$table} WHERE {$idField}=? AND key=? LIMIT 1");
    $select->execute(array($id, $key));
    $existing = $select->fetchColumn();
    if ($existing !== false) {
        $database->prepare("UPDATE {$table} SET value=?, modifyTime=? WHERE id=?")->execute(array($value, $now, $existing));
        return;
    }
    $database->prepare("INSERT INTO {$table} ({$idField}, key, value, createTime, modifyTime) VALUES (?, ?, ?, ?, ?)")
        ->execute(array($id, $key, $value, $now, $now));
}

function find_or_create_folder(PDO $database, string $name, int $parentId, string $parentLevel, int $now): int {
    $query = $database->prepare("SELECT sourceID FROM io_source WHERE parentID=? AND name=? AND isFolder=1 AND isDelete=0 LIMIT 1");
    $query->execute(array($parentId, $name));
    $existing = $query->fetchColumn();
    if ($existing !== false) return (int) $existing;
    $hash = substr(strtr(base64_encode(random_bytes(6)), '+/', '-_'), 0, 8);
    $database->prepare('INSERT INTO io_source (sourceHash,targetType,targetID,createUser,modifyUser,isFolder,name,fileType,parentID,parentLevel,fileID,isDelete,size,createTime,modifyTime,viewTime) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
        ->execute(array($hash, 1, 1, 1, 1, 1, $name, '', $parentId, $parentLevel, 0, 0, 0, $now, $now, $now));
    return (int) $database->lastInsertId();
}

function write_document(PDO $database, string $dataRoot, int $folderId, string $parentLevel,
                        string $displayName, string $sourceFile, array $aliases, int $now): void {
    $content = file_get_contents($sourceFile);
    if ($content === false || $content === '') throw new RuntimeException('无法读取资料：' . $sourceFile);
    list($md5, $simpleHash) = content_hash($content);
    $extension = file_extension($displayName);
    $candidates = array_merge(array($displayName), $aliases);
    $placeholders = implode(',', array_fill(0, count($candidates), '?'));
    $query = $database->prepare("SELECT s.sourceID,s.fileID,f.path FROM io_source s JOIN io_file f ON f.fileID=s.fileID WHERE s.parentID=? AND s.isFolder=0 AND s.isDelete=0 AND s.name IN ({$placeholders}) ORDER BY s.sourceID LIMIT 1");
    $query->execute(array_merge(array($folderId), $candidates));
    $existing = $query->fetch(PDO::FETCH_ASSOC);

    if ($existing) {
        $physicalPath = storage_path($dataRoot, (string) $existing['path']);
        if (!is_dir(dirname($physicalPath))) mkdir(dirname($physicalPath), 0775, true);
        file_put_contents($physicalPath, $content);
        $database->prepare('UPDATE io_file SET name=?,size=?,hashSimple=?,hashMd5=?,modifyTime=? WHERE fileID=?')
            ->execute(array($displayName, strlen($content), $simpleHash, $md5, $now, $existing['fileID']));
        $database->prepare('UPDATE io_source SET name=?,fileType=?,size=?,modifyUser=1,modifyTime=? WHERE sourceID=?')
            ->execute(array($displayName, $extension, strlen($content), $now, $existing['sourceID']));
        return;
    }

    $relativeDirectory = date('Ym/d');
    $storageName = bin2hex(random_bytes(10));
    $virtualPath = '{io:1}/' . $relativeDirectory . '/' . $storageName;
    $physicalPath = storage_path($dataRoot, $virtualPath);
    if (!is_dir(dirname($physicalPath))) mkdir(dirname($physicalPath), 0775, true);
    file_put_contents($physicalPath, $content);
    $database->prepare('INSERT INTO io_file (name,size,ioType,path,hashSimple,hashMd5,linkCount,createTime,modifyTime) VALUES (?,?,?,?,?,?,?,?,?)')
        ->execute(array($displayName, strlen($content), 1, $virtualPath, $simpleHash, $md5, 1, $now, $now));
    $fileId = (int) $database->lastInsertId();
    $sourceHash = substr(strtr(base64_encode(random_bytes(6)), '+/', '-_'), 0, 8);
    $database->prepare('INSERT INTO io_source (sourceHash,targetType,targetID,createUser,modifyUser,isFolder,name,fileType,parentID,parentLevel,fileID,isDelete,size,createTime,modifyTime,viewTime) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
        ->execute(array($sourceHash, 1, 1, 1, 1, 0, $displayName, $extension, $folderId, $parentLevel, $fileId, 0, strlen($content), $now, $now, $now));
}

function find_task(PDO $database, int $projectId, string $name): ?int {
    $query = $database->prepare('SELECT taskID FROM plugin_project_task WHERE projectID=? AND name=? LIMIT 1');
    $query->execute(array($projectId, $name));
    $value = $query->fetchColumn();
    return $value === false ? null : (int) $value;
}

function upsert_task(PDO $database, int $projectId, int $parentId, array $task, int $now): int {
    $taskId = find_task($database, $projectId, $task['name']);
    if ($taskId === null) {
        $database->prepare('INSERT INTO plugin_project_task (projectID,pid,name,desc,status,isList,sort,ownerUser,createUser,modifyUser,createTime,modifyTime) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)')
            ->execute(array($projectId, $parentId, $task['name'], $task['desc'], 1, 0, $task['sort'], $task['owner'], 1, $task['owner'] ?: 1, $task['created'], $task['modified']));
        $taskId = (int) $database->lastInsertId();
    } else {
        $database->prepare('UPDATE plugin_project_task SET desc=?,ownerUser=?,modifyUser=?,modifyTime=? WHERE taskID=?')
            ->execute(array($task['desc'], $task['owner'], $task['owner'] ?: 1, $task['modified'], $taskId));
    }
    foreach (array(
        'taskCheck' => $task['finished'] ? '1' : '0',
        'taskStatus' => $task['status'],
        'taskPercent' => (string) $task['percent'],
        'taskLevel' => $task['priority'],
        'timeFrom' => (string) $task['start'],
        'timeTo' => (string) $task['due'],
    ) as $key => $value) upsert_meta($database, 'plugin_project_task_meta', 'taskID', $taskId, $key, $value, $now);
    return $taskId;
}

function ensure_log(PDO $database, int $projectId, int $taskId, int $userId, string $type, string $description, int $time): void {
    $query = $database->prepare('SELECT id FROM plugin_project_log WHERE projectID=? AND taskID=? AND logType=? AND desc=? LIMIT 1');
    $query->execute(array($projectId, $taskId, $type, $description));
    if ($query->fetchColumn() !== false) return;
    $database->prepare('INSERT INTO plugin_project_log (projectID,taskID,userID,logType,desc,createTime,modifyTime) VALUES (?,?,?,?,?,?,?)')
        ->execute(array($projectId, $taskId, $userId, $type, $description, $time, $time));
}

$markerType = 'kodagent_project_seed';
$markerKey = 'binjiang_planning_v2';
$marker = $database->prepare('SELECT value FROM system_option WHERE type=? AND key=? LIMIT 1');
$marker->execute(array($markerType, $markerKey));
if ($marker->fetchColumn() !== false && !$force) {
    fwrite(STDOUT, "滨江项目数据基线已存在；如需重建请显式传入 --force\n");
    exit(0);
}

if (!$apply) {
    fwrite(STDOUT, "预览：将完善项目任务、活动日志、项目资料和共享制度资料；传入 --apply 后执行。\n");
    exit(0);
}

$now = unix_time('2026-08-16 16:30:00');
$projectFolderQuery = $database->prepare("SELECT value FROM plugin_project_meta WHERE projectID=? AND key='fileSourceID' LIMIT 1");
$projectFolderQuery->execute(array($projectId));
$projectFolderId = (int) $projectFolderQuery->fetchColumn();
if ($projectFolderId <= 0) throw new RuntimeException('项目未配置资料目录');
$projectFolderLevel = ',0,5,' . $projectFolderId . ',';

$projectDocuments = array(
    '01_滨江片区项目任务书与工作边界_v1.2.md' => array('aliases' => array('滨江片区规划任务书.md')),
    '02_滨江片区现状调研与数据缺口清单_v1.1.txt' => array('aliases' => array('滨江片区现状资料汇编.txt')),
    '03_更新单元划分与空间设计方案说明_v0.8.md' => array('aliases' => array()),
    '04_滨江片区综合交通提升专题分析_v1.0.docx' => array('aliases' => array('滨江片区交通问题分析.docx')),
    '05_滨江片区规划指标测算与底线约束_v1.0.xlsx' => array('aliases' => array('滨江片区规划指标表.xlsx')),
    '06_滨江片区总体进度计划与里程碑_v1.0.xlsx' => array('aliases' => array()),
    '07_中期成果汇报会准备方案_v1.0.docx' => array('aliases' => array()),
    '08_外部专家咨询会问题清单与会议纪要_v0.9.md' => array('aliases' => array()),
    '09_项目风险与协调事项台账_v1.0.md' => array('aliases' => array()),
    '10_成果版本与资料交接清单_v1.0.md' => array('aliases' => array()),
    '11_中期成果汇报口径与对外材料保密说明_v1.0.txt' => array('aliases' => array()),
    '12_技术审查意见及整改闭环台账_v1.0.xlsx' => array('aliases' => array()),
);

$tasks = array(
    array('name'=>'现状资料收集与目录整理','owner'=>3,'priority'=>'normal','percent'=>100,'status'=>'finished','finished'=>true,'start'=>unix_time('2026-07-20 09:00:00'),'due'=>unix_time('2026-07-27 18:00:00'),'modified'=>unix_time('2026-07-27 17:30:00'),'sort'=>10,'desc'=>'已完成现状用地、人口、道路、公共服务设施和近三年审批项目的目录整理；已形成资料版本和数据缺口清单，后续新增资料必须纳入引用台账。'),
    array('name'=>'人口与用地现状分析','owner'=>8,'priority'=>'normal','percent'=>100,'status'=>'finished','finished'=>true,'start'=>unix_time('2026-07-22 09:00:00'),'due'=>unix_time('2026-08-02 18:00:00'),'modified'=>unix_time('2026-08-02 16:00:00'),'sort'=>20,'desc'=>'已完成常住人口、建设用地、公共服务设施服务半径的阶段分析；中期汇报使用 2025 年底基线数据，并明确两处在建地块不纳入现状结论。'),
    array('name'=>'历史建筑与公共服务设施踏勘','owner'=>6,'priority'=>'hight','percent'=>65,'status'=>'blocked','finished'=>false,'start'=>unix_time('2026-07-28 09:00:00'),'due'=>unix_time('2026-08-10 18:00:00'),'modified'=>unix_time('2026-08-09 17:00:00'),'sort'=>30,'desc'=>'已完成主要公共服务设施踏勘和初步历史建筑点位核对；老码头片区保护范围与更新单元边界尚待技术审查室核验，任务逾期但未完成。'),
    array('name'=>'更新单元划分与实施条件研判','owner'=>3,'priority'=>'very_hight','percent'=>70,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-03 09:00:00'),'due'=>unix_time('2026-08-18 18:00:00'),'modified'=>unix_time('2026-08-15 18:30:00'),'sort'=>10,'desc'=>'已形成六个更新单元初步边界及实施条件判断；老码头更新段需等待历史建筑保护范围核验，人民路综合整治段需结合在建地块施工计划后确定近期动作。'),
    array('name'=>'滨水公共空间节点设计','owner'=>4,'priority'=>'hight','percent'=>55,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-05 09:00:00'),'due'=>unix_time('2026-08-26 18:00:00'),'modified'=>unix_time('2026-08-14 16:00:00'),'sort'=>20,'desc'=>'已完成滨江公园东侧和老码头片区两个重点节点的现状问题梳理；下一步与慢行断点贯通方案和周边更新界面同步深化。'),
    array('name'=>'重点地块方案比选','owner'=>4,'priority'=>'normal','percent'=>30,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-08 09:00:00'),'due'=>unix_time('2026-09-03 18:00:00'),'modified'=>unix_time('2026-08-13 15:30:00'),'sort'=>30,'desc'=>'正在比较滨水活力段与老码头更新段的近期实施路径；方案比选需同时说明公共效益、实施主体、资金平衡和历史建筑保护边界。'),
    array('name'=>'道路交通问题识别','owner'=>9,'priority'=>'hight','percent'=>100,'status'=>'finished','finished'=>true,'start'=>unix_time('2026-07-25 09:00:00'),'due'=>unix_time('2026-08-04 18:00:00'),'modified'=>unix_time('2026-08-04 17:00:00'),'sort'=>10,'desc'=>'已完成滨江大道—人民路交叉口、滨水慢行断点和老旧小区停车矛盾的基础识别；问题清单已作为综合交通专题 v1.0 的事实依据。'),
    array('name'=>'微循环与慢行系统优化方案','owner'=>9,'priority'=>'very_hight','percent'=>55,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-05 09:00:00'),'due'=>unix_time('2026-08-23 18:00:00'),'modified'=>unix_time('2026-08-15 17:00:00'),'sort'=>20,'desc'=>'正在形成微循环、慢行连续化和公交站点优化的组合建议；施工期交通组织需待两处在建地块出入口和施工时序确认后补充。'),
    array('name'=>'停车组织与施工期交通保障建议','owner'=>0,'priority'=>'hight','percent'=>10,'status'=>'waiting_owner','finished'=>false,'start'=>unix_time('2026-08-10 09:00:00'),'due'=>unix_time('2026-08-30 18:00:00'),'modified'=>unix_time('2026-08-12 11:00:00'),'sort'=>30,'desc'=>'已明确老旧小区夜间停车、消防通道和施工期组织是专家会必须回应的问题；当前尚未明确主责人，项目例会需完成责任分派。'),
    array('name'=>'GIS 数据整理与图层标准化','owner'=>5,'priority'=>'normal','percent'=>100,'status'=>'finished','finished'=>true,'start'=>unix_time('2026-07-29 09:00:00'),'due'=>unix_time('2026-08-06 18:00:00'),'modified'=>unix_time('2026-08-06 16:30:00'),'sort'=>10,'desc'=>'已完成中期分析所需基础图层、坐标基准和图层命名规范整理；敏感底图已单独标识，不进入专家会外发材料。'),
    array('name'=>'规划指标校核与数据缺口清单','owner'=>5,'priority'=>'hight','percent'=>60,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-07 09:00:00'),'due'=>unix_time('2026-08-20 18:00:00'),'modified'=>unix_time('2026-08-16 10:30:00'),'sort'=>20,'desc'=>'正在校核公共服务覆盖、慢行连续率和更新单元实施条件等指标；未确认的施工计划和补测客流数据已列入数据缺口，不能作为最终测算依据。'),
    array('name'=>'项目资料版本与权限核验','owner'=>2,'priority'=>'hight','percent'=>75,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-08 09:00:00'),'due'=>unix_time('2026-08-18 18:00:00'),'modified'=>unix_time('2026-08-16 14:00:00'),'sort'=>30,'desc'=>'已建立项目资料版本与交接清单初稿；专家会外发包需在 8 月 18 日前完成图表文字一致性、敏感资料脱敏和引用版本核验。'),
    array('name'=>'中期成果汇报材料编制','owner'=>7,'priority'=>'very_hight','percent'=>50,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-09 09:00:00'),'due'=>unix_time('2026-08-16 18:00:00'),'modified'=>unix_time('2026-08-16 15:30:00'),'sort'=>10,'desc'=>'已完成“事实依据—问题判断—方案比选—待决事项”汇报框架；等待交通专题施工期假设、历史建筑核验说明和资料版本台账后形成专家会正式材料。'),
    array('name'=>'技术审查意见汇总与闭环','owner'=>10,'priority'=>'hight','percent'=>35,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-12 09:00:00'),'due'=>unix_time('2026-08-28 18:00:00'),'modified'=>unix_time('2026-08-15 16:30:00'),'sort'=>20,'desc'=>'已将内部预备会意见整理为 A-01 至 A-04 整改台账；专家咨询会后需补充意见采纳情况、修订计划和技术审查材料。'),
    array('name'=>'经营计划与成果交付协调','owner'=>11,'priority'=>'normal','percent'=>20,'status'=>'not_started','finished'=>false,'start'=>unix_time('2026-08-18 09:00:00'),'due'=>unix_time('2026-09-07 18:00:00'),'modified'=>unix_time('2026-08-12 15:00:00'),'sort'=>30,'desc'=>'待中期技术路线稳定后，明确近期实施建议、成果交付节点和对外沟通计划；当前不将未确认的实施项目写入交付承诺。'),
    array('name'=>'最终成果文件整理','owner'=>2,'priority'=>'normal','percent'=>5,'status'=>'not_started','finished'=>false,'start'=>unix_time('2026-09-01 09:00:00'),'due'=>unix_time('2026-09-13 18:00:00'),'modified'=>unix_time('2026-08-12 10:00:00'),'sort'=>10,'desc'=>'规划成果、图件、表格、审查意见和版本台账将在技术审查后统一整理；当前仅建立归档目录和交接规则。'),
    array('name'=>'资料归档与交接清单','owner'=>2,'priority'=>'normal','percent'=>5,'status'=>'not_started','finished'=>false,'start'=>unix_time('2026-09-08 09:00:00'),'due'=>unix_time('2026-09-18 18:00:00'),'modified'=>unix_time('2026-08-12 10:00:00'),'sort'=>20,'desc'=>'将按成果目录、版本清单、来源说明、审查闭环和权限核验形成交接包；项目成员调整时同步复核资料目录与知识索引状态。'),
);

$newTasks = array(
    array('name'=>'外部专家咨询会组织与材料核验','owner'=>7,'priority'=>'very_hight','percent'=>50,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-14 09:00:00'),'due'=>unix_time('2026-08-20 12:00:00'),'modified'=>unix_time('2026-08-16 15:00:00'),'created'=>unix_time('2026-08-14 09:00:00'),'sort'=>40,'desc'=>'负责 8 月 20 日专家咨询会的议程、问题清单、参会材料和外发版本核验；会前必须确认资料保密边界、交通专题阶段性假设和待决事项表述。'),
    array('name'=>'专家意见整理与方案修订计划','owner'=>10,'priority'=>'hight','percent'=>0,'status'=>'not_started','finished'=>false,'start'=>unix_time('2026-08-20 16:00:00'),'due'=>unix_time('2026-08-28 18:00:00'),'modified'=>unix_time('2026-08-14 17:00:00'),'created'=>unix_time('2026-08-14 17:00:00'),'sort'=>50,'desc'=>'专家会结束后归集意见，区分采纳、部分采纳和待进一步论证事项；形成责任人、证据文件和审查节点明确的修订计划。'),
    array('name'=>'项目例会行动项跟踪','owner'=>3,'priority'=>'normal','percent'=>40,'status'=>'in_progress','finished'=>false,'start'=>unix_time('2026-08-12 09:00:00'),'due'=>unix_time('2026-08-28 18:00:00'),'modified'=>unix_time('2026-08-16 16:00:00'),'created'=>unix_time('2026-08-12 09:00:00'),'sort'=>60,'desc'=>'持续跟踪资料缺口、跨专业依赖、专家会准备和审查意见整改；每次例会记录已决定事项、待外部输入事项及责任时限。'),
);

$activity = array(
    array('2026-08-09 17:00:00', 4, 6, 'task.edit', '现场踏勘已完成主要公共服务设施核查；老码头片区历史建筑保护范围待技术审查室确认，任务风险上报。'),
    array('2026-08-12 11:00:00', 12, 1, 'task.edit', '例会确认停车组织与施工期交通保障需单列回应，目前待项目负责人明确主责人。'),
    array('2026-08-12 15:00:00', 20, 11, 'task.edit', '经营交付工作包暂按中期技术路线稳定后启动，未对外承诺未确认的实施项目。'),
    array('2026-08-14 16:00:00', 7, 4, 'task.edit', '滨水公共空间节点完成第一轮问题梳理，需与慢行断点贯通方案联动深化。'),
    array('2026-08-15 16:30:00', 19, 10, 'task.metaSet', '内部预备会形成 A-01 至 A-04 技术意见，已录入整改闭环台账。'),
    array('2026-08-15 17:00:00', 11, 9, 'task.edit', '交通组确认施工期组织需等待两处在建地块出入口和施工时序，专家会材料采用阶段性假设表述。'),
    array('2026-08-15 18:30:00', 6, 3, 'task.edit', '六个更新单元初步边界完成，老码头和人民路两个单元保留待外部确认事项。'),
    array('2026-08-16 10:30:00', 15, 5, 'task.metaSet', '指标校核完成第一轮，施工计划和周末客流补测仍列为数据缺口。'),
    array('2026-08-16 14:00:00', 16, 2, 'task.edit', '项目资料版本与权限核验完成初稿，专家会外发包待三方核验。'),
    array('2026-08-16 15:30:00', 18, 7, 'task.edit', '中期汇报采用四段式结构，等待交通专题补充和保护范围核验说明。'),
);

if (!is_dir($sourceArgument . '/project') || !is_dir($sourceArgument . '/policy')) throw new RuntimeException('资料生成目录结构不完整');

$database->beginTransaction();
try {
    $database->prepare('UPDATE plugin_project SET desc=?, modifyUser=1, modifyTime=? WHERE projectID=?')
        ->execute(array('围绕滨江片区存量空间更新、综合交通提升和近期实施安排开展的规划院协同项目；当前处于中期成果和专家咨询会准备阶段。', $now, $projectId));
    foreach (array(
        'progress' => '42',
        'timeFrom' => (string) unix_time('2026-07-20 09:00:00'),
        'timeTo' => (string) unix_time('2026-09-18 18:00:00'),
        'taskFinishType' => 'taskCheck',
        'taskShowOnlySelf' => '0',
        'projectDataVersion' => 'binjiang-planning-v2',
    ) as $key => $value) upsert_meta($database, 'plugin_project_meta', 'projectID', $projectId, $key, $value, $now);

    foreach ($projectDocuments as $name => $spec) {
        write_document($database, $dataRoot, $projectFolderId, $projectFolderLevel, $name,
            $sourceArgument . '/project/' . $name, $spec['aliases'], $now);
    }

    $policyFolderId = find_or_create_folder($database, '[policy] 规划技术管理制度库', 5, ',0,5,', $now);
    $policyFolderLevel = ',0,5,' . $policyFolderId . ',';
    foreach (glob($sourceArgument . '/policy/*') as $file) {
        write_document($database, $dataRoot, $policyFolderId, $policyFolderLevel, basename($file), $file, array(), $now);
    }

    $taskIds = array();
    foreach ($tasks as $task) $taskIds[$task['name']] = upsert_task($database, $projectId, (int) (find_task($database, $projectId, $task['name']) ? $database->query('SELECT pid FROM plugin_project_task WHERE taskID=' . (int) find_task($database, $projectId, $task['name']))->fetchColumn() : 0), $task + array('created'=>$task['start']), $now);
    $reviewGroupId = find_task($database, $projectId, '成果审查与报批');
    if (!$reviewGroupId) throw new RuntimeException('未找到成果审查与报批工作包');
    foreach ($newTasks as $task) $taskIds[$task['name']] = upsert_task($database, $projectId, $reviewGroupId, $task, $now);

    foreach ($activity as $event) ensure_log($database, $projectId, $event[1], $event[2], $event[3], $event[4], unix_time($event[0]));
    ensure_log($database, $projectId, $taskIds['外部专家咨询会组织与材料核验'], 7, 'task.add', '已建立专家咨询会组织与材料核验任务，纳入中期成果审查工作包。', unix_time('2026-08-14 09:00:00'));
    ensure_log($database, $projectId, $taskIds['专家意见整理与方案修订计划'], 10, 'task.add', '已建立专家意见整理与方案修订计划任务，待专家会后启动。', unix_time('2026-08-14 17:00:00'));
    ensure_log($database, $projectId, $taskIds['项目例会行动项跟踪'], 3, 'task.add', '已建立项目例会行动项跟踪任务，持续记录跨专业协同和风险闭环。', unix_time('2026-08-12 09:00:00'));

    $markerQuery = $database->prepare('SELECT id FROM system_option WHERE type=? AND key=? LIMIT 1');
    $markerQuery->execute(array($markerType, $markerKey));
    $markerId = $markerQuery->fetchColumn();
    if ($markerId !== false) {
        $database->prepare('UPDATE system_option SET value=?,modifyTime=? WHERE id=?')->execute(array('2026-08-16T16:30:00+08:00', $now, $markerId));
    } else {
        $database->prepare('INSERT INTO system_option (type,key,value,createTime,modifyTime) VALUES (?,?,?,?,?)')
            ->execute(array($markerType, $markerKey, '2026-08-16T16:30:00+08:00', $now, $now));
    }
    $database->commit();
    fwrite(STDOUT, json_encode(array('projectId'=>$projectId, 'projectFolderId'=>$projectFolderId, 'policyFolderId'=>$policyFolderId, 'status'=>'SUCCEEDED'), JSON_UNESCAPED_UNICODE) . PHP_EOL);
} catch (Throwable $error) {
    if ($database->inTransaction()) $database->rollBack();
    fwrite(STDERR, '初始化失败：' . $error->getMessage() . PHP_EOL);
    exit(1);
}
