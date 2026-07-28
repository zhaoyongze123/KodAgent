-- 审批附件按当前可道云用户权限读取所需的用户令牌字段。
-- 令牌由 MyBatis EncryptTypeHandler 加密后写入，禁止在接口响应中返回。
-- MySQL 8.4 不支持 ADD COLUMN IF NOT EXISTS，使用元数据判断保证脚本幂等。
SET @kod_access_token_sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE `system_kod_sso_user_bind` ADD COLUMN `kod_access_token` varchar(2048) DEFAULT NULL COMMENT ''可道云用户令牌(加密)'' AFTER `raw_profile_json`',
    'SELECT 1'
  )
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'system_kod_sso_user_bind'
    AND column_name = 'kod_access_token'
);
PREPARE kod_access_token_stmt FROM @kod_access_token_sql;
EXECUTE kod_access_token_stmt;
DEALLOCATE PREPARE kod_access_token_stmt;
