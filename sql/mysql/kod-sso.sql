CREATE TABLE IF NOT EXISTS `system_kod_sso_user_bind` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '编号',
  `user_id` bigint NOT NULL COMMENT '本地用户编号',
  `kod_user_id` varchar(128) NOT NULL COMMENT '可道云用户唯一标识',
  `kod_username` varchar(128) NOT NULL DEFAULT '' COMMENT '可道云用户名',
  `kod_nickname` varchar(128) NOT NULL DEFAULT '' COMMENT '可道云昵称',
  `raw_profile_json` text COMMENT '可道云原始用户信息',
  `kod_access_token` varchar(2048) DEFAULT NULL COMMENT '可道云用户令牌(加密)',
  `creator` varchar(64) DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  `tenant_id` bigint NOT NULL DEFAULT '0' COMMENT '租户编号',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_system_kod_sso_user_bind_kod_user_id` (`kod_user_id`),
  UNIQUE KEY `uk_system_kod_sso_user_bind_kod_username` (`kod_username`),
  UNIQUE KEY `uk_system_kod_sso_user_bind_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='可道云用户绑定';

UPDATE `system_role`
SET `name` = '普通用户',
    `code` = 'common_user',
    `remark` = '普通用户'
WHERE `id` = 2 AND `tenant_id` = 1;

UPDATE `system_role`
SET `name` = '部门管理员',
    `code` = 'dept_admin',
    `remark` = '部门管理员'
WHERE `id` = 3 AND `tenant_id` = 1;
