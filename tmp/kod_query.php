<?php
$db = new PDO('sqlite:/var/www/html/data/system/2dUCpY5rdwGC.php');
foreach (['group', 'user', 'user_group'] as $table) {
    echo "---{$table}---\n";
    foreach ($db->query('PRAGMA table_info("' . $table . '")') as $row) {
        echo $row['name'] . '|' . $row['type'] . "\n";
    }
}
echo "---users---\n";
foreach ($db->query("SELECT * FROM \"user\" WHERE name LIKE '%苏%' OR nickname LIKE '%苏%'") as $row) {
    echo json_encode($row, JSON_UNESCAPED_UNICODE) . "\n";
}
echo "---groups---\n";
foreach ($db->query("SELECT * FROM \"group\" WHERE name LIKE '%行政%' OR name LIKE '%财务%'") as $row) {
    echo json_encode($row, JSON_UNESCAPED_UNICODE) . "\n";
}
echo "---user_group---\n";
foreach ($db->query('SELECT * FROM user_group') as $row) {
    echo json_encode($row, JSON_UNESCAPED_UNICODE) . "\n";
}
