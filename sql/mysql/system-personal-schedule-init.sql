-- 个人日程模块初始化 SQL
-- 执行前请确认当前库为 ruoyi-vue-pro 对应数据库

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for system_personal_schedule
-- ----------------------------
CREATE TABLE IF NOT EXISTS `system_personal_schedule` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '日程编号',
  `title` varchar(200) NOT NULL COMMENT '日程标题',
  `start_time` datetime NOT NULL COMMENT '开始时间',
  `end_time` datetime NOT NULL COMMENT '结束时间',
  `owner_user_id` bigint NOT NULL COMMENT '所属用户编号',
  `location` varchar(255) DEFAULT NULL COMMENT '地址',
  `description` varchar(1000) DEFAULT NULL COMMENT '文字描述',
  `other_participants` varchar(500) DEFAULT NULL COMMENT '外部参与者',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_owner_time` (`owner_user_id`, `start_time`, `end_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人日程表';

-- ----------------------------
-- Table structure for system_personal_schedule_attendee
-- ----------------------------
CREATE TABLE IF NOT EXISTS `system_personal_schedule_attendee` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `schedule_id` bigint NOT NULL COMMENT '日程编号',
  `user_id` bigint NOT NULL COMMENT '用户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_schedule` (`schedule_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人日程参与人表';

-- ----------------------------
-- Menu
-- 说明：
-- 1. 菜单挂在独立“日程”模块下，默认分配给管理员和普通员工角色
-- 2. 如果普通员工角色 id 不是 2，请同步调整 role_id
-- ----------------------------
SET @schedule_root_id := 30061;
SET @personal_schedule_menu_id := 30060;

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @schedule_root_id, '日程', '', 1, 40, 0, '/schedule', 'mdi:calendar-month-outline', NULL, NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @schedule_root_id);

UPDATE `system_menu`
SET `parent_id` = @schedule_root_id, `path` = 'calendar', `sort` = 1,
    `component` = 'system/personal-schedule/index', `component_name` = 'ScheduleCenterCalendar'
WHERE `id` = @personal_schedule_menu_id;

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @personal_schedule_menu_id, '个人日程', '', 2, 1, @schedule_root_id, 'calendar', 'mdi:calendar-account', 'system/personal-schedule/index', 'ScheduleCenterCalendar', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @personal_schedule_menu_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @schedule_root_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @schedule_root_id AND `deleted` = b'0');

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, @schedule_root_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = @schedule_root_id AND `deleted` = b'0');

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @personal_schedule_menu_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @personal_schedule_menu_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, @personal_schedule_menu_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = @personal_schedule_menu_id);

SET FOREIGN_KEY_CHECKS = 1;
