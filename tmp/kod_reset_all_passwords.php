<?php
$db = new PDO('sqlite:/var/www/html/data/system/2dUCpY5rdwGC.php');
$db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$hash = md5('Aa123456');
$db->beginTransaction();
$stmt = $db->prepare('UPDATE "user" SET password = ?, modifyTime = ?');
$stmt->execute([$hash, time()]);
$db->commit();
$total = (int)$db->query('SELECT COUNT(*) FROM "user"')->fetchColumn();
$matched = (int)$db->query('SELECT COUNT(*) FROM "user" WHERE password = ' . $db->quote($hash))->fetchColumn();
echo json_encode([
    'total_users' => $total,
    'passwords_updated' => $stmt->rowCount(),
    'hash_matches' => $matched,
], JSON_UNESCAPED_UNICODE) . "\n";
