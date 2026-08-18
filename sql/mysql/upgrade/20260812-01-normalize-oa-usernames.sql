-- Planning Institute OA 2026-08-12-01
-- The user nickname remains the Chinese display name. The username is the
-- lower-case pinyin login account and the only OA/KodBox SSO match key.
--
-- This mapping was generated from the active users on server 103. Existing
-- KodBox accounts take precedence: admin, houbinchao, bingyanping, zhanglin,
-- suli, zhuxinjie and huanghua. Same-name users get stable numeric suffixes.
-- The script never changes user IDs, nicknames, passwords, departments, roles,
-- or approval history.

DROP TEMPORARY TABLE IF EXISTS oa_username_migration;
CREATE TEMPORARY TABLE oa_username_migration (
  user_id bigint NOT NULL PRIMARY KEY,
  username varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  UNIQUE KEY uk_oa_username_migration_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO oa_username_migration (user_id, username) VALUES
  (1, 'admin'),
  (107, 'yunai'),
  (108, 'yunai1'),
  (109, 'yunai2'),
  (110, 'xiaowang'),
  (111, 'ceshiyonghu'),
  (113, 'yudao1'),
  (149, 'oaputongyonghu2'),
  (150, 'xitongguanliyuan'),
  (215, 'houbinchao'),
  (216, 'qianaimei'),
  (217, 'maqian'),
  (218, 'bingyanping'),
  (219, 'zhanghua'),
  (220, 'zhanglin'),
  (221, 'puweimin'),
  (222, 'lidan'),
  (223, 'suli'),
  (224, 'luoxiang'),
  (225, 'mouyuntao'),
  (226, 'yanji'),
  (227, 'hezhihua'),
  (228, 'lihaojie'),
  (229, 'zhuxinjie'),
  (230, 'laizhiyong'),
  (231, 'jinchen'),
  (232, 'caohuiting'),
  (233, 'mashuyun'),
  (234, 'boyijie'),
  (235, 'huangxiaoyi'),
  (236, 'zhangaining'),
  (237, 'maodan'),
  (238, 'caimeng'),
  (239, 'guoyun'),
  (240, 'zhuyi'),
  (241, 'xujiaqi'),
  (242, 'shengyiwen'),
  (243, 'chenjie'),
  (244, 'xuchun'),
  (245, 'fuyuntong'),
  (246, 'jinxiaohui'),
  (247, 'huangyubo'),
  (248, 'xiangyuewei'),
  (249, 'hukexin'),
  (250, 'luoya'),
  (251, 'xuxinyi'),
  (252, 'huangjinghe'),
  (253, 'wangsiqi'),
  (254, 'lilehui'),
  (255, 'zhaoli'),
  (256, 'xuxuanxuan'),
  (257, 'zhangkunzhe'),
  (258, 'lilangdi'),
  (259, 'hehongfu'),
  (260, 'zhangweili'),
  (261, 'huangliping'),
  (262, 'zhangchi'),
  (263, 'taozhenyu'),
  (264, 'shenyu'),
  (265, 'zhangjingfang'),
  (266, 'wangchunping'),
  (267, 'yangzhenlei'),
  (268, 'xueyouyi'),
  (269, 'chenlingyun'),
  (270, 'sunruimin'),
  (271, 'liuchao'),
  (272, 'wushuang'),
  (273, 'lichunhui'),
  (274, 'xuhailing'),
  (275, 'zhangyihui'),
  (276, 'huanghua'),
  (277, 'gujun'),
  (280, 'jiangxinyi'),
  (281, 'wengpeifeng'),
  (282, 'xuxinyun');

-- Abort before changing data when the target set is incomplete or a target
-- account belongs to another active user.
DROP PROCEDURE IF EXISTS validate_oa_username_migration;
DELIMITER //
CREATE PROCEDURE validate_oa_username_migration()
BEGIN
  IF (SELECT COUNT(*) FROM system_users WHERE deleted = b'0') <>
     (SELECT COUNT(*) FROM oa_username_migration) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'OA username migration does not cover every active user';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM system_users AS existing_user
    INNER JOIN oa_username_migration AS target ON target.username = existing_user.username
    WHERE existing_user.deleted = b'0'
      AND existing_user.id <> target.user_id
  ) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'OA username migration conflicts with an active user';
  END IF;
END//
DELIMITER ;
CALL validate_oa_username_migration();
DROP PROCEDURE validate_oa_username_migration;

START TRANSACTION;

-- Move through deterministic temporary values so usernames can safely swap.
UPDATE system_users AS user
INNER JOIN oa_username_migration AS target ON target.user_id = user.id
SET user.username = CONCAT('__oa_migrate_', user.id)
WHERE user.deleted = b'0'
  AND user.username <> target.username;

UPDATE system_users AS user
INNER JOIN oa_username_migration AS target ON target.user_id = user.id
SET user.username = target.username
WHERE user.deleted = b'0'
  AND user.username <> target.username;

COMMIT;

-- MySQL 8 generated column: active usernames are unique, while a logically
-- deleted historical account does not block re-creating the same account.
SET @active_username_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'system_users'
    AND column_name = 'active_username'
);
SET @add_active_username_column_sql := IF(
  @active_username_column_exists = 0,
  'ALTER TABLE system_users ADD COLUMN active_username varchar(30) GENERATED ALWAYS AS (IF(deleted = b''0'', username, NULL)) STORED',
  'SELECT 1'
);
PREPARE add_active_username_column_statement FROM @add_active_username_column_sql;
EXECUTE add_active_username_column_statement;
DEALLOCATE PREPARE add_active_username_column_statement;

SET @active_username_index_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'system_users'
    AND index_name = 'uk_system_users_active_username'
);
SET @add_active_username_index_sql := IF(
  @active_username_index_exists = 0,
  'ALTER TABLE system_users ADD UNIQUE KEY uk_system_users_active_username (active_username)',
  'SELECT 1'
);
PREPARE add_active_username_index_statement FROM @add_active_username_index_sql;
EXECUTE add_active_username_index_statement;
DEALLOCATE PREPARE add_active_username_index_statement;

SELECT user.id, user.username AS login_username, user.nickname
FROM system_users AS user
WHERE user.deleted = b'0'
ORDER BY user.id;
