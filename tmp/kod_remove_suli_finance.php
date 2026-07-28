<?php
$db = new PDO('sqlite:/var/www/html/data/system/2dUCpY5rdwGC.php');
$db->beginTransaction();
$stmt = $db->prepare('DELETE FROM user_group WHERE userID = ? AND groupID = ?');
$stmt->execute([28, 40]);
echo 'deleted=' . $stmt->rowCount() . "\n";
$db->commit();
foreach ($db->query('SELECT userID,groupID FROM user_group WHERE userID=28 ORDER BY groupID') as $row) {
    echo $row['userID'] . ':' . $row['groupID'] . "\n";
}
