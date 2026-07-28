-- 修复 stage 环境文件访问域名与历史头像 URL
-- 适用场景：浏览器访问头像或本地文件时跳到 127.0.0.1:48080 导致拒绝连接

SET @old_domain = 'http://127.0.0.1:48080';
SET @new_domain = 'http://124.221.4.228:48080';

-- 1. 修复会通过后端转发返回文件 URL 的文件配置
UPDATE `infra_file_config`
SET `config` = JSON_SET(`config`, '$.domain', @new_domain)
WHERE JSON_UNQUOTE(JSON_EXTRACT(`config`, '$.domain')) = @old_domain;

-- 2. 修复系统用户历史头像 URL
UPDATE `system_users`
SET `avatar` = REPLACE(`avatar`, @old_domain, @new_domain)
WHERE `avatar` LIKE CONCAT(@old_domain, '/%');

-- 3. 修复示例联系人等历史头像 URL，避免同类页面继续报错
SET @contact_table_exists = (
  SELECT COUNT(*)
  FROM information_schema.TABLES
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'yudao_demo01_contact'
);
SET @contact_sql = IF(
  @contact_table_exists > 0,
  CONCAT(
    'UPDATE `yudao_demo01_contact` ',
    'SET `avatar` = REPLACE(`avatar`, ''', @old_domain, ''', ''', @new_domain, ''') ',
    'WHERE `avatar` LIKE ''', @old_domain, '/%'';'
  ),
  'SELECT 1;'
);
PREPARE stmt_contact FROM @contact_sql;
EXECUTE stmt_contact;
DEALLOCATE PREPARE stmt_contact;
