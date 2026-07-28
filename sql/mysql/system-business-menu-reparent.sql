-- OA 业务菜单归属调整
-- 目标：系统管理只保留基础管理；会议室、日程、党务文件进入各自独立模块。
-- 仅调整菜单、路由及角色权限归属，不删除页面、接口和业务数据。

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

SET @meeting_root_id := 30050;
SET @meeting_manage_id := 30041;
SET @meeting_booking_id := 30051;
SET @meeting_schedule_id := 30052;
SET @schedule_root_id := 30061;
SET @schedule_calendar_id := 30060;
SET @party_root_id := 30070;
SET @party_manage_id := 3101;
SET @party_my_id := 30071;

-- 会议室：共用一个顶级模块；管理入口只分配给管理员。
UPDATE `system_menu`
SET `name` = '会议室', `parent_id` = 0, `path` = '/meeting-room',
    `component` = NULL, `component_name` = NULL, `sort` = 30,
    `status` = 0, `visible` = b'1', `always_show` = b'1', `update_time` = NOW()
WHERE `id` = @meeting_root_id;

UPDATE `system_menu`
SET `name` = '会议室管理', `parent_id` = @meeting_root_id, `path` = 'manage',
    `component` = 'system/meeting-room/index', `component_name` = 'MeetingCenterManage',
    `sort` = 1, `status` = 0, `visible` = b'1', `update_time` = NOW()
WHERE `id` = @meeting_manage_id;

UPDATE `system_menu`
SET `parent_id` = @meeting_root_id, `path` = 'booking', `sort` = 2,
    `component` = 'system/meeting-booking/index', `component_name` = 'MeetingCenterBooking',
    `permission` = '', `status` = 0, `visible` = b'1', `update_time` = NOW()
WHERE `id` = @meeting_booking_id;

UPDATE `system_menu`
SET `parent_id` = @meeting_root_id, `path` = 'schedule', `sort` = 3,
    `component` = 'system/meeting-booking/schedule', `component_name` = 'MeetingCenterSchedule',
    `status` = 0, `visible` = b'1', `update_time` = NOW()
WHERE `id` = @meeting_schedule_id;

-- 保留旧菜单编号用于兼容，但不再从“系统管理”展示。
UPDATE `system_menu`
SET `status` = 1, `visible` = b'0', `update_time` = NOW()
WHERE `id` IN (30040, 30042, 30043);

UPDATE `system_menu` SET `parent_id` = @meeting_booking_id, `update_time` = NOW()
WHERE `id` IN (300421, 300422, 300423);
UPDATE `system_menu` SET `parent_id` = @meeting_schedule_id, `update_time` = NOW()
WHERE `id` = 300424;

-- 日程：个人日程挂入独立“日程”模块。
INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @schedule_root_id, '日程', '', 1, 40, 0, '/schedule', 'mdi:calendar-month-outline', NULL, NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @schedule_root_id);

UPDATE `system_menu`
SET `parent_id` = @schedule_root_id, `path` = 'calendar', `sort` = 1,
    `component` = 'system/personal-schedule/index', `component_name` = 'ScheduleCenterCalendar',
    `status` = 0, `visible` = b'1', `update_time` = NOW()
WHERE `id` = @schedule_calendar_id;

-- 党务：管理端和“我的党务文件”同属党务管理模块。
INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @party_root_id, '党务管理', '', 1, 50, 0, '/party-file', 'ep:folder-opened', NULL, NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @party_root_id);

UPDATE `system_menu`
SET `name` = '党务文件管理', `parent_id` = @party_root_id, `path` = 'manage',
    `component` = 'system/party-file/index', `component_name` = 'PartyFileCenterManage',
    `permission` = 'system:party-file:query', `sort` = 1,
    `status` = 0, `visible` = b'1', `update_time` = NOW()
WHERE `id` = @party_manage_id;

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @party_my_id, '我的党务文件', '', 2, 2, @party_root_id, 'my', 'mdi:file-account-outline', 'system/party-file/my-index', 'PartyFileCenterMy', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @party_my_id);

-- 管理员：拥有三个模块及管理功能。
INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, '1', NOW(), '1', NOW(), b'0', 1
FROM (
  SELECT @meeting_root_id AS menu_id UNION ALL SELECT @meeting_manage_id
  UNION ALL SELECT @meeting_booking_id UNION ALL SELECT @meeting_schedule_id
  UNION ALL SELECT @schedule_root_id UNION ALL SELECT @schedule_calendar_id
  UNION ALL SELECT @party_root_id UNION ALL SELECT @party_manage_id
  UNION ALL SELECT @party_my_id UNION ALL SELECT 3102 UNION ALL SELECT 3103
  UNION ALL SELECT 3104 UNION ALL SELECT 3105 UNION ALL SELECT 3106
  UNION ALL SELECT 3107 UNION ALL SELECT 3108 UNION ALL SELECT 3109
) menus
WHERE NOT EXISTS (
  SELECT 1 FROM `system_role_menu`
  WHERE `role_id` = 1 AND `menu_id` = menus.menu_id AND `deleted` = b'0'
);

-- 普通用户：只保留预定、排期、个人日程和“我的党务文件”。
INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, menu_id, '1', NOW(), '1', NOW(), b'0', 1
FROM (
  SELECT @meeting_root_id AS menu_id UNION ALL SELECT @meeting_booking_id
  UNION ALL SELECT @meeting_schedule_id UNION ALL SELECT @schedule_root_id
  UNION ALL SELECT @schedule_calendar_id UNION ALL SELECT @party_root_id
  UNION ALL SELECT @party_my_id
) menus
WHERE NOT EXISTS (
  SELECT 1 FROM `system_role_menu`
  WHERE `role_id` = 2 AND `menu_id` = menus.menu_id AND `deleted` = b'0'
);

UPDATE `system_role_menu`
SET `deleted` = b'1', `update_time` = NOW()
WHERE `role_id` = 2
  AND `menu_id` IN (30040, 30041, 30042, 30043, 300411, 300412, 300413, 300421, 300422, 300423, 3101, 3102, 3103, 3104, 3105, 3106, 3107, 3108, 3109)
  AND `deleted` = b'0';

SET FOREIGN_KEY_CHECKS = 1;
