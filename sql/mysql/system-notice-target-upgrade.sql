CREATE TABLE IF NOT EXISTS `system_notice_target` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `notice_id` bigint NOT NULL COMMENT '公告编号',
  `target_type` tinyint NOT NULL COMMENT '发布类型 1全员 2用户 3部门 4角色',
  `target_id` bigint NULL DEFAULT NULL COMMENT '发布对象编号',
  `creator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '创建者',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updater` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '' COMMENT '更新者',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `deleted` bit(1) NOT NULL DEFAULT b'0' COMMENT '是否删除',
  PRIMARY KEY (`id`) USING BTREE,
  KEY `idx_notice_id` (`notice_id`) USING BTREE,
  KEY `idx_target` (`target_type`, `target_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '通知公告发布对象表';

INSERT INTO `system_notice_target` (`notice_id`, `target_type`, `target_id`, `creator`, `create_time`, `updater`, `update_time`, `deleted`)
SELECT `id`, 1, NULL, 'system', NOW(), 'system', NOW(), b'0'
FROM `system_notice` n
WHERE NOT EXISTS (
  SELECT 1 FROM `system_notice_target` t WHERE t.`notice_id` = n.`id`
);
