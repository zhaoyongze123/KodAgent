-- 规划院 OA 2026-08-10-01
-- 为可道云 SSO 绑定记录增加加密后的访问令牌字段。
-- 使用 information_schema 判断，重复执行不会重复加列。

SET @kod_access_token_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'system_kod_sso_user_bind'
    AND column_name = 'kod_access_token'
);

SET @kod_access_token_sql := IF(
  @kod_access_token_column_exists = 0,
  'ALTER TABLE system_kod_sso_user_bind ADD COLUMN kod_access_token varchar(2048) NULL COMMENT ''KodBox SSO access token'' AFTER raw_profile_json',
  'SELECT 1'
);

PREPARE kod_access_token_statement FROM @kod_access_token_sql;
EXECUTE kod_access_token_statement;
DEALLOCATE PREPARE kod_access_token_statement;
