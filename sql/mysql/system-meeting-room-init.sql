-- 会议室预定模块初始化 SQL
-- 执行前请确认当前库为 ruoyi-vue-pro 对应数据库

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for system_meeting_room
-- ----------------------------
CREATE TABLE IF NOT EXISTS `system_meeting_room` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '会议室编号',
  `name` varchar(100) NOT NULL COMMENT '会议室名称',
  `location` varchar(255) NOT NULL COMMENT '所在位置',
  `capacity` int NOT NULL COMMENT '容纳人数',
  `equipment` varchar(500) DEFAULT NULL COMMENT '设备配置，逗号分隔',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '状态',
  `sort` int NOT NULL DEFAULT 0 COMMENT '排序号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_status_sort` (`status`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会议室表';

-- ----------------------------
-- Table structure for system_meeting_booking
-- ----------------------------
CREATE TABLE IF NOT EXISTS `system_meeting_booking` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '预定编号',
  `subject` varchar(200) NOT NULL COMMENT '会议主题',
  `meeting_room_id` bigint NOT NULL COMMENT '会议室编号',
  `start_time` datetime NOT NULL COMMENT '开始时间',
  `end_time` datetime NOT NULL COMMENT '结束时间',
  `applicant_user_id` bigint NOT NULL COMMENT '申请人编号',
  `remark` varchar(500) DEFAULT NULL COMMENT '备注',
  `status` tinyint NOT NULL DEFAULT 1 COMMENT '状态',
  `force_conflict` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否忽略冲突提醒保存',
  `cancel_reason` varchar(500) DEFAULT NULL COMMENT '取消原因',
  `cancel_type` tinyint DEFAULT NULL COMMENT '取消类型',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_room_time` (`meeting_room_id`, `start_time`, `end_time`),
  KEY `idx_applicant` (`applicant_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会议室预定表';

-- ----------------------------
-- Table structure for system_meeting_booking_attendee
-- ----------------------------
CREATE TABLE IF NOT EXISTS `system_meeting_booking_attendee` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `booking_id` bigint NOT NULL COMMENT '预定编号',
  `user_id` bigint NOT NULL COMMENT '用户编号',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT 0 COMMENT '租户编号',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_booking` (`booking_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会议室预定参会人表';

-- ----------------------------
-- Dict type
-- ----------------------------
INSERT INTO `system_dict_type` (`id`, `name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT 3001, '会议室设备', 'system_meeting_room_equipment', 0, '会议室设备字典', '1', NOW(), '1', NOW(), b'0', '1970-01-01 00:00:00'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_type` WHERE `type` = 'system_meeting_room_equipment');

INSERT INTO `system_dict_type` (`id`, `name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT 3002, '会议室预定状态', 'system_meeting_booking_status', 0, '会议室预定状态字典', '1', NOW(), '1', NOW(), b'0', '1970-01-01 00:00:00'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_type` WHERE `type` = 'system_meeting_booking_status');

INSERT INTO `system_dict_type` (`id`, `name`, `type`, `status`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `deleted_time`)
SELECT 3003, '会议室取消类型', 'system_meeting_booking_cancel_type', 0, '会议室取消类型字典', '1', NOW(), '1', NOW(), b'0', '1970-01-01 00:00:00'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_type` WHERE `type` = 'system_meeting_booking_cancel_type');

-- ----------------------------
-- Dict data
-- ----------------------------
INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30011, 1, '投影仪', 'projector', 'system_meeting_room_equipment', 0, 'primary', '', '投影仪', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_room_equipment' AND `value` = 'projector');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30012, 2, '电视', 'tv', 'system_meeting_room_equipment', 0, 'success', '', '电视', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_room_equipment' AND `value` = 'tv');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30013, 3, '视频会议设备', 'video_conference', 'system_meeting_room_equipment', 0, 'warning', '', '视频会议设备', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_room_equipment' AND `value` = 'video_conference');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30014, 4, '白板', 'whiteboard', 'system_meeting_room_equipment', 0, 'info', '', '白板', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_room_equipment' AND `value` = 'whiteboard');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30021, 1, '已生效', '1', 'system_meeting_booking_status', 0, 'success', '', '已生效', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_booking_status' AND `value` = '1');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30022, 2, '已取消', '2', 'system_meeting_booking_status', 0, 'danger', '', '已取消', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_booking_status' AND `value` = '2');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30031, 1, '用户取消', '1', 'system_meeting_booking_cancel_type', 0, 'primary', '', '用户取消', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_booking_cancel_type' AND `value` = '1');

INSERT INTO `system_dict_data` (`id`, `sort`, `label`, `value`, `dict_type`, `status`, `color_type`, `css_class`, `remark`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 30032, 2, '管理员取消', '2', 'system_meeting_booking_cancel_type', 0, 'danger', '', '管理员取消', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_dict_data` WHERE `dict_type` = 'system_meeting_booking_cancel_type' AND `value` = '2');

-- ----------------------------
-- Init meeting rooms
-- 说明：
-- 1. 仅初始化默认会议室，不覆盖已有设备、备注等业务字段
-- 2. 通过名称幂等插入；已存在时只补齐基础容量、位置、排序和启用状态
-- ----------------------------
INSERT INTO `system_meeting_room`
(`name`, `location`, `capacity`, `equipment`, `remark`, `status`, `sort`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT '二楼会议室 36人', '二楼', 36, NULL, '', 0, 10, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (
    SELECT 1 FROM `system_meeting_room`
    WHERE `name` = '二楼会议室 36人' AND `deleted` = b'0'
);

UPDATE `system_meeting_room`
SET `location` = '二楼', `capacity` = 36, `status` = 0, `sort` = 10, `deleted` = b'0'
WHERE `name` = '二楼会议室 36人';

INSERT INTO `system_meeting_room`
(`name`, `location`, `capacity`, `equipment`, `remark`, `status`, `sort`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT '二楼会议室 14人', '二楼', 14, NULL, '', 0, 20, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (
    SELECT 1 FROM `system_meeting_room`
    WHERE `name` = '二楼会议室 14人' AND `deleted` = b'0'
);

UPDATE `system_meeting_room`
SET `location` = '二楼', `capacity` = 14, `status` = 0, `sort` = 20, `deleted` = b'0'
WHERE `name` = '二楼会议室 14人';

INSERT INTO `system_meeting_room`
(`name`, `location`, `capacity`, `equipment`, `remark`, `status`, `sort`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT '二楼会议室8人', '二楼', 8, NULL, '', 0, 30, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (
    SELECT 1 FROM `system_meeting_room`
    WHERE `name` = '二楼会议室8人' AND `deleted` = b'0'
);

UPDATE `system_meeting_room`
SET `location` = '二楼', `capacity` = 8, `status` = 0, `sort` = 30, `deleted` = b'0'
WHERE `name` = '二楼会议室8人';

INSERT INTO `system_meeting_room`
(`name`, `location`, `capacity`, `equipment`, `remark`, `status`, `sort`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT '博士后实践基地会议室10人', '博士后实践基地', 10, NULL, '', 0, 40, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (
    SELECT 1 FROM `system_meeting_room`
    WHERE `name` = '博士后实践基地会议室10人' AND `deleted` = b'0'
);

UPDATE `system_meeting_room`
SET `location` = '博士后实践基地', `capacity` = 10, `status` = 0, `sort` = 40, `deleted` = b'0'
WHERE `name` = '博士后实践基地会议室10人';

INSERT INTO `system_meeting_room`
(`name`, `location`, `capacity`, `equipment`, `remark`, `status`, `sort`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT '四楼会议室 100+8人', '四楼', 108, NULL, '', 0, 50, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (
    SELECT 1 FROM `system_meeting_room`
    WHERE `name` = '四楼会议室 100+8人' AND `deleted` = b'0'
);

UPDATE `system_meeting_room`
SET `location` = '四楼', `capacity` = 108, `status` = 0, `sort` = 50, `deleted` = b'0'
WHERE `name` = '四楼会议室 100+8人';

-- ----------------------------
-- Menu
-- 说明：
-- 1. 管理员和普通用户共用顶级“会议室”模块，管理员额外看到“会议室管理”
-- 2. 如果你的系统里系统管理菜单 id 不是 1，请修改 @system_parent_id
-- 3. 如果你的环境普通员工角色 id 不是 2，请同步修改下面 role_id
-- ----------------------------
SET @system_parent_id := 1;
SET @admin_menu_root_id := 30040;
SET @admin_menu_room_id := 30041;
SET @admin_menu_booking_id := 30042;
SET @admin_menu_schedule_id := 30043;
SET @user_menu_root_id := 30050;
SET @user_menu_booking_id := 30051;
SET @user_menu_schedule_id := 30052;

UPDATE `system_menu` SET `component` = 'system/meeting-room/index'
WHERE `id` = @admin_menu_room_id;

UPDATE `system_menu` SET `component` = 'system/meeting-booking/index'
WHERE `id` = @admin_menu_booking_id;

UPDATE `system_menu` SET `component` = 'system/meeting-booking/schedule'
WHERE `id` = @admin_menu_schedule_id;

UPDATE `system_menu` SET `component` = NULL
WHERE `id` = @user_menu_root_id;

UPDATE `system_menu` SET `component` = 'system/meeting-booking/index'
WHERE `id` = @user_menu_booking_id;

UPDATE `system_menu` SET `component` = 'system/meeting-booking/schedule'
WHERE `id` = @user_menu_schedule_id;

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @admin_menu_root_id, '会议室预定', '', 1, 80, @system_parent_id, 'meeting-center', 'mdi:meeting-room', NULL, NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @admin_menu_root_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @admin_menu_room_id, '会议室管理', 'system:meeting-room:query', 2, 1, @admin_menu_root_id, 'meeting-room', 'mdi:door-open', 'system/meeting-room/index', 'SystemMeetingRoom', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @admin_menu_room_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @admin_menu_booking_id, '会议室预定', 'system:meeting-booking:query', 2, 2, @admin_menu_root_id, 'meeting-booking', 'mdi:calendar-check', 'system/meeting-booking/index', 'SystemMeetingBooking', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @admin_menu_booking_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @admin_menu_schedule_id, '会议室排期', 'system:meeting-booking:schedule', 2, 3, @admin_menu_root_id, 'meeting-schedule', 'mdi:calendar-month', 'system/meeting-booking/schedule', 'SystemMeetingSchedule', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @admin_menu_schedule_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @user_menu_root_id, '会议室', '', 1, 30, 0, '/meeting-room', 'mdi:meeting-room', NULL, NULL, 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @user_menu_root_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @user_menu_booking_id, '会议室预定', '', 2, 1, @user_menu_root_id, 'booking', 'mdi:calendar-check', 'system/meeting-booking/index', 'MeetingCenterBooking', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @user_menu_booking_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT @user_menu_schedule_id, '会议室排期', 'system:meeting-booking:schedule', 2, 2, @user_menu_root_id, 'schedule', 'mdi:calendar-month', 'system/meeting-booking/schedule', 'MeetingCenterSchedule', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = @user_menu_schedule_id);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300411, '会议室新增', 'system:meeting-room:create', 3, 1, @admin_menu_room_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300411);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300412, '会议室修改', 'system:meeting-room:update', 3, 2, @admin_menu_room_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300412);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300413, '会议室删除', 'system:meeting-room:delete', 3, 3, @admin_menu_room_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300413);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300421, '预定查询', 'system:meeting-booking:query', 3, 1, @admin_menu_booking_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300421);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300422, '预定修改', 'system:meeting-booking:update', 3, 2, @admin_menu_booking_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300422);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300423, '预定删除', 'system:meeting-booking:delete', 3, 3, @admin_menu_booking_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300423);

INSERT INTO `system_menu` (`id`, `name`, `permission`, `type`, `sort`, `parent_id`, `path`, `icon`, `component`, `component_name`, `status`, `visible`, `keep_alive`, `always_show`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT 300424, '排期查看', 'system:meeting-booking:schedule', 3, 4, @admin_menu_schedule_id, '', '', '', '', 0, b'1', b'1', b'1', '1', NOW(), '1', NOW(), b'0'
WHERE NOT EXISTS (SELECT 1 FROM `system_menu` WHERE `id` = 300424);

-- ----------------------------
-- Role menu
-- 说明：
-- 1. 超级管理员需要显式分配菜单，否则不会出现在权限菜单树中
-- 2. 普通员工需要拥有预定、排期和会议室精简列表相关权限，才能完成自助预约
-- ----------------------------
INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @admin_menu_root_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @admin_menu_root_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @admin_menu_room_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @admin_menu_room_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @admin_menu_booking_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @admin_menu_booking_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, @admin_menu_schedule_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = @admin_menu_schedule_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300411, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300411);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300412, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300412);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300413, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300413);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300421, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300421);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300422, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300422);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300423, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300423);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, 300424, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 1 AND `menu_id` = 300424);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, @user_menu_root_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = @user_menu_root_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, @user_menu_booking_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = @user_menu_booking_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, @user_menu_schedule_id, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = @user_menu_schedule_id);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, 300421, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = 300421);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, 300422, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = 300422);

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 2, 300424, '1', NOW(), '1', NOW(), b'0', 1
WHERE NOT EXISTS (SELECT 1 FROM `system_role_menu` WHERE `role_id` = 2 AND `menu_id` = 300424);

-- 统一归属到顶级“会议室”模块，旧管理员目录仅保留兼容编号并停止展示
UPDATE `system_menu`
SET `parent_id` = @user_menu_root_id, `path` = 'manage', `sort` = 1,
    `component_name` = 'MeetingCenterManage', `status` = 0, `visible` = b'1'
WHERE `id` = @admin_menu_room_id;

UPDATE `system_menu`
SET `sort` = 2, `component_name` = 'MeetingCenterBooking', `permission` = ''
WHERE `id` = @user_menu_booking_id;

UPDATE `system_menu`
SET `sort` = 3, `component_name` = 'MeetingCenterSchedule'
WHERE `id` = @user_menu_schedule_id;

UPDATE `system_menu` SET `status` = 1, `visible` = b'0'
WHERE `id` IN (@admin_menu_root_id, @admin_menu_booking_id, @admin_menu_schedule_id);

UPDATE `system_menu` SET `parent_id` = @user_menu_booking_id
WHERE `id` IN (300421, 300422, 300423);
UPDATE `system_menu` SET `parent_id` = @user_menu_schedule_id
WHERE `id` = 300424;

INSERT INTO `system_role_menu` (`role_id`, `menu_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`, `tenant_id`)
SELECT 1, menu_id, '1', NOW(), '1', NOW(), b'0', 1
FROM (
  SELECT @user_menu_root_id AS menu_id
  UNION ALL SELECT @user_menu_booking_id
  UNION ALL SELECT @user_menu_schedule_id
) menus
WHERE NOT EXISTS (
  SELECT 1 FROM `system_role_menu`
  WHERE `role_id` = 1 AND `menu_id` = menus.menu_id AND `deleted` = b'0'
);

UPDATE `system_role_menu`
SET `deleted` = b'1', `update_time` = NOW()
WHERE `role_id` = 2
  AND `menu_id` IN (@admin_menu_root_id, @admin_menu_room_id, @admin_menu_booking_id,
                    @admin_menu_schedule_id, 300411, 300412, 300413, 300421, 300422, 300423)
  AND `deleted` = b'0';

SET FOREIGN_KEY_CHECKS = 1;
