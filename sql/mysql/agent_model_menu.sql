-- Agent 模型管理后台菜单与权限。
INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7500, 'Agent 模型管理', '', 2, 30, 0, 'agent/model', 'ant-design:robot-filled', 'agent/model/index', 'AgentModel', 0, b'1', b'1', b'1', 'admin', NOW(), 'admin', NOW(), b'0'
FROM dual WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7500);
INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7501, 'Agent 模型查询', 'system:agent-model:query', 3, 1, 7500, '', '', '', '', 0, b'1', b'1', b'0', 'admin', NOW(), 'admin', NOW(), b'0'
FROM dual WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7501);
INSERT INTO system_menu (id, name, permission, type, sort, parent_id, path, icon, component, component_name, status, visible, keep_alive, always_show, creator, create_time, updater, update_time, deleted)
SELECT 7502, 'Agent 模型管理', 'system:agent-model:manage', 3, 2, 7500, '', '', '', '', 0, b'1', b'1', b'0', 'admin', NOW(), 'admin', NOW(), b'0'
FROM dual WHERE NOT EXISTS (SELECT 1 FROM system_menu WHERE id = 7502);
