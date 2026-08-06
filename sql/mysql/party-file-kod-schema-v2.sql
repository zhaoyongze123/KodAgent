-- Party-file KodBox schema v2.
--
-- The Java mapper reads these columns for token refresh.  Keep this migration
-- idempotent so it can be applied to an existing OA database as well as a
-- freshly imported dump.
-- MySQL versions used by existing OA deployments do not all support
-- `ADD COLUMN IF NOT EXISTS`, so use information_schema checks instead.
SET @schema_name = DATABASE();
SET @sql = IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'party_file_kod_source' AND column_name = 'service_username'),
  'SELECT 1',
  'ALTER TABLE `party_file_kod_source` ADD COLUMN `service_username` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT ''服务账号'' AFTER `access_token`'
);
PREPARE party_file_schema_stmt FROM @sql; EXECUTE party_file_schema_stmt; DEALLOCATE PREPARE party_file_schema_stmt;

SET @sql = IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'party_file_kod_source' AND column_name = 'service_password'),
  'SELECT 1',
  'ALTER TABLE `party_file_kod_source` ADD COLUMN `service_password` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT ''服务密码(加密)'' AFTER `service_username`'
);
PREPARE party_file_schema_stmt FROM @sql; EXECUTE party_file_schema_stmt; DEALLOCATE PREPARE party_file_schema_stmt;

SET @sql = IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'party_file_kod_source' AND column_name = 'token_expire_time'),
  'SELECT 1',
  'ALTER TABLE `party_file_kod_source` ADD COLUMN `token_expire_time` datetime NULL DEFAULT NULL COMMENT ''令牌过期时间'' AFTER `service_password`'
);
PREPARE party_file_schema_stmt FROM @sql; EXECUTE party_file_schema_stmt; DEALLOCATE PREPARE party_file_schema_stmt;

CREATE TABLE IF NOT EXISTS `party_file_kod_attachment` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
  `file_id` bigint NOT NULL COMMENT '本地文件记录编号',
  `kod_source_id` bigint NOT NULL COMMENT '可道云来源编号',
  `kod_file_path` varchar(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '可道云文件路径',
  `kod_parent_path` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '可道云父目录路径',
  `creator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updater` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` bit(1) NOT NULL DEFAULT b'0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_party_file_kod_attachment_file_id` (`file_id`),
  KEY `idx_party_file_kod_attachment_source_id` (`kod_source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='党务文件可道云附件映射表';

-- Stable defaults used by the Agent's party-file CREATE workflow.  Do not
-- assume numeric IDs: existing OA databases may already contain custom
-- categories (for example "联调党务分类"), so resolve by name at runtime.
-- These inserts are idempotent and never overwrite an administrator's row.
INSERT INTO `party_file_category`
  (`name`, `parent_id`, `sort`, `status`, `creator`, `updater`)
SELECT '组织建设', 0, 10, 0, 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM `party_file_category` WHERE `name` = '组织建设' AND `deleted` = b'0');
INSERT INTO `party_file_category`
  (`name`, `parent_id`, `sort`, `status`, `creator`, `updater`)
SELECT '会议活动', 0, 20, 0, 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM `party_file_category` WHERE `name` = '会议活动' AND `deleted` = b'0');
INSERT INTO `party_file_category`
  (`name`, `parent_id`, `sort`, `status`, `creator`, `updater`)
SELECT '制度规范', 0, 30, 0, 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM `party_file_category` WHERE `name` = '制度规范' AND `deleted` = b'0');
INSERT INTO `party_file_category`
  (`name`, `parent_id`, `sort`, `status`, `creator`, `updater`)
SELECT '通知公告', 0, 40, 0, 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM `party_file_category` WHERE `name` = '通知公告' AND `deleted` = b'0');
INSERT INTO `party_file_category`
  (`name`, `parent_id`, `sort`, `status`, `creator`, `updater`)
SELECT '上级文件', 0, 50, 0, 'system', 'system'
WHERE NOT EXISTS (SELECT 1 FROM `party_file_category` WHERE `name` = '上级文件' AND `deleted` = b'0');

-- The Agent Draft/Approval facts live in PostgreSQL, while party_file and
-- party_file_target live in MySQL. This narrow ledger is the only additional
-- fact needed to reconcile a crash between those databases. It is not a
-- generic workflow table and must stay scoped to party-file commits.
CREATE TABLE IF NOT EXISTS `agent_party_file_commit` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '党务文件 Agent 提交台账编号',
  `tenant_id` bigint NOT NULL COMMENT '租户编号',
  `owner_user_id` bigint NOT NULL COMMENT '操作用户编号',
  `draft_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Agent 草稿编号',
  `approval_id` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Agent 审批编号',
  `operation_id` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Agent Operation 编号',
  `idempotency_key` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '提交幂等键',
  `operation` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'CREATE/UPDATE/DELETE',
  `status` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'PROCESSING' COMMENT 'PROCESSING/SUCCEEDED',
  `party_file_id` bigint NULL DEFAULT NULL COMMENT '已提交的党务文件编号',
  `result_data` json NULL COMMENT '业务提交结果',
  `creator` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updater` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT '',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `deleted` bit(1) NOT NULL DEFAULT b'0',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `uk_agent_party_file_commit_key` (`tenant_id`, `owner_user_id`, `idempotency_key`) USING BTREE,
  KEY `idx_agent_party_file_commit_draft` (`tenant_id`, `owner_user_id`, `draft_id`) USING BTREE,
  KEY `idx_agent_party_file_commit_operation` (`tenant_id`, `owner_user_id`, `operation_id`) USING BTREE
) ENGINE = InnoDB CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '党务文件 Agent 提交幂等台账';
