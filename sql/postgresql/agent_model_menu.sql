-- Agent 模型管理后台菜单与权限。
-- 执行一次即可；重复执行不会产生重复菜单。
INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7500, 'Agent 模型管理', '', 2, 30, 0, 'agent/model', 'ant-design:robot-filled', 'agent/model/index', 'AgentModel', 0, '1', '1', '1', 'admin', CURRENT_TIMESTAMP, 'admin', CURRENT_TIMESTAMP, '0'
WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7500);

INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7501, 'Agent 模型查询', 'system:agent-model:query', 3, 1, 7500, '', '', '', '', 0, '1', '1', '0', 'admin', CURRENT_TIMESTAMP, 'admin', CURRENT_TIMESTAMP, '0'
WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7501);

INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7502, 'Agent 模型管理', 'system:agent-model:manage', 3, 2, 7500, '', '', '', '', 0, '1', '1', '0', 'admin', CURRENT_TIMESTAMP, 'admin', CURRENT_TIMESTAMP, '0'
WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7502);
