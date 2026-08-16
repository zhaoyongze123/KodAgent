-- 项目智能助手的 OA 入口权限。
--
-- 此权限只决定用户能否调用 Project Provider；项目、任务和资料的可见性仍由
-- KodCloud project 插件按实时成员关系与 taskShowOnlySelf 复核，不能把它当作
-- 项目数据授权本身。

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 7503, '项目智能助手查询', 'system:agent-project:read', 3, 3, 7500, '', '', '', '', 0, b'1', b'1', b'0', 'admin', NOW(), 'admin', NOW(), b'0'
FROM dual WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 7503);

INSERT INTO `system_menu`
(`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 7504, '项目智能助手管理', 'system:agent-project:manage', 3, 4, 7500, '', '', '', '', 0, b'1', b'1', b'0', 'admin', NOW(), 'admin', NOW(), b'0'
FROM dual WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 7504);

-- 普通用户仅获得只读入口。是否能看到某个项目、任务或资料不由本关系决定。
INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, 7503, 'admin', NOW(), 'admin', NOW(), b'0', 1
FROM dual WHERE NOT EXISTS (
    SELECT 1 FROM `system_role_menu`
    WHERE `role_id` = 2 AND `menu_id` = 7503 AND `tenant_id` = 1 AND `deleted` = b'0'
);
