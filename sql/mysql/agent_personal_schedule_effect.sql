-- Canonical OA MySQL migration for the personal-schedule business Effect.
-- This file is applied by scripts/migrate-oa-mysql-schema.sh and the
-- oa-mysql-schema-migrate Compose job. It is deliberately separate from the
-- personal-schedule menu/table bootstrap and from the immutable base dump.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `agent_schema_migration` (
  `version` varchar(128) NOT NULL,
  `applied_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent OA MySQL schema versions';

CREATE TABLE IF NOT EXISTS `agent_personal_schedule_effect` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Effect ledger id',
  `tenant_id` bigint NOT NULL COMMENT 'Tenant id',
  `owner_user_id` bigint NOT NULL COMMENT 'Schedule owner',
  `operation_id` varchar(128) DEFAULT NULL COMMENT 'Python Operation id',
  `draft_id` varchar(128) NOT NULL COMMENT 'Agent draft id',
  `idempotency_key` varchar(128) NOT NULL COMMENT 'Stable business Effect key',
  `operation` varchar(16) NOT NULL COMMENT 'CREATE, UPDATE or CANCEL',
  `status` varchar(32) NOT NULL COMMENT 'PROCESSING or SUCCEEDED',
  `result_data` json DEFAULT NULL COMMENT 'Committed business result',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_agent_personal_schedule_effect_key` (`tenant_id`, `owner_user_id`, `idempotency_key`),
  KEY `idx_agent_personal_schedule_effect_draft` (`tenant_id`, `owner_user_id`, `draft_id`),
  KEY `idx_agent_personal_schedule_effect_operation` (`tenant_id`, `owner_user_id`, `operation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Agent personal schedule business Effect ledger';

INSERT INTO `agent_schema_migration` (`version`)
VALUES ('agent_personal_schedule_effect_v1')
ON DUPLICATE KEY UPDATE `version` = VALUES(`version`);
