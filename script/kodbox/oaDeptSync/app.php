<?php

/**
 * Sync Kodbox groups, group roots and group membership for the OA file space.
 * The endpoint is intentionally root-only and never deletes file content.
 */
class oaDeptSyncPlugin extends PluginBase {
    /**
     * Initialize the small reference organization captured from server 228.
     * This is separate from the normal sync endpoint because it creates only
     * missing groups/users and never removes existing data.
     */
    public function initializeReference() {
        if (!KodUser::isLogin()) {
            $this->json(false, 'login required');
        }
        KodUser::checkRoot();
        if (Input::get('confirm', 'require', '0') !== '1') {
            $this->json(false, 'execution requires confirm=1');
        }

        $rootGroupID = trim((string)Input::get('rootGroupId', 'require', '1'));
        $result = $this->initializeReferenceOrganization($rootGroupID);
        $this->json(true, 'reference organization initialized', $result);
    }

    public function verifyReferenceCredentials() {
        if (!KodUser::isLogin()) {
            $this->json(false, 'login required');
        }
        KodUser::checkRoot();
        $file = DATA_PATH . 'system/oaDeptSync-initial-credentials.txt';
        if (!is_readable($file)) {
            $this->json(false, 'credential file not found');
        }
        $verified = 0;
        $failed = array();
        foreach (file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            list($name, $password) = explode("\t", $line, 2);
            $user = Model('User')->userLoginCheck($name, KodUser::parsePass($password), true);
            if (is_array($user)) {
                $verified++;
            } else {
                $failed[] = $name;
            }
        }
        $this->json(empty($failed), 'credential verification completed', array(
            'verifiedCount' => $verified,
            'failedUsers' => $failed,
        ));
    }

    /**
     * Internal entry used by the deployment operator. Passwords are generated
     * per new account and recorded only in a 0600 file inside the data volume.
     */
    public function initializeReferenceOrganization($rootGroupID = '1') {
        $rootGroupID = (string)$rootGroupID;
        $root = Model('Group')->where(array('groupID' => $rootGroupID))
            ->field('groupID,name,parentID')->find();
        if (!$root || (string)$root['parentID'] !== '0') {
            return array('success' => false, 'message' => 'invalid root group');
        }

        $allGroups = Model('Group')->field('groupID,name,parentID,sort')->select();
        $groupByParentAndName = array();
        foreach ($allGroups as $group) {
            $key = (string)$group['parentID'] . '|' . (string)$group['name'];
            $groupByParentAndName[$key] = (string)$group['groupID'];
        }

        $groupPlan = array(
            array('分管领导', '院部', 1),
            array('张华', '分管领导', 1),
            array('邴燕萍', '分管领导', 2),
            array('钱爱梅', '分管领导', 3),
            array('马倩', '分管领导', 4),
            array('交通市政规划所', '张华', 1),
            array('技术审查室', '张华', 2),
            array('综合科（计划经营）', '张华', 3),
            array('综合科（行政/财务）', '邴燕萍', 1),
            array('行政办公', '综合科（行政/财务）', 1),
            array('财务管理', '综合科（行政/财务）', 2),
            array('乡村规划所', '钱爱梅', 1),
            array('城市更新规划所', '钱爱梅', 2),
            array('城市设计所', '钱爱梅', 3),
            array('总体规划和专项规划所', '钱爱梅', 4),
            array('数字城市规划所', '马倩', 1),
            array('规划研究室', '马倩', 2),
            array('计划经营', '综合科（计划经营）', 1),
            array('院长', '院部', 99),
        );

        $groupIds = array('院部' => $rootGroupID);
        $createdGroupCount = 0;
        $reusedGroupCount = 0;
        foreach ($groupPlan as $item) {
            list($name, $parentName, $sort) = $item;
            if (!isset($groupIds[$parentName])) {
                return array('success' => false, 'message' => 'missing parent group: ' . $parentName);
            }
            $parentID = (string)$groupIds[$parentName];
            $key = $parentID . '|' . $name;
            if (isset($groupByParentAndName[$key])) {
                $groupIds[$name] = $groupByParentAndName[$key];
                $reusedGroupCount++;
                continue;
            }

            $groupID = Model('Group')->groupAdd(array(
                'name' => $name,
                'parentID' => intval($parentID),
                'sort' => intval($sort),
                'sizeMax' => 0,
            ));
            if (!$groupID) {
                return array('success' => false, 'message' => 'failed to create group: ' . $name);
            }
            $groupID = (string)$groupID;
            $groupIds[$name] = $groupID;
            $groupByParentAndName[$key] = $groupID;
            $createdGroupCount++;
        }

        // The root may predate this plugin, so ensure every native group space.
        $createdSourceCount = 0;
        foreach ($groupIds as $groupID) {
            $source = Model('Source')->where(array(
                'targetType' => 2,
                'targetID' => $groupID,
                'parentID' => 0,
                'isDelete' => 0,
            ))->field('sourceID')->find();
            if ($source) {
                $sourceID = intval($source['sourceID']);
            } else {
                $sourceID = Model('Source')->groupRootAdd($groupID);
                if (!$sourceID) {
                    return array('success' => false, 'message' => 'failed to create group space: ' . $groupID);
                }
                $createdSourceCount++;
            }
            if (!is_cli()) {
                $this->createDefaultGroupFolders($sourceID);
            }
        }

        $userPlan = array(
            array('huanghua', '黄华', '行政办公'),
            array('suli', '苏莉', '行政办公'),
            array('bingyanping', '邴燕萍', '邴燕萍'),
            array('houbinchao', '侯斌超', '院长'),
            array('zhanglin', '张龄', '技术审查室'),
            array('zhuxinjie', '朱新捷', '技术审查室'),
        );
        $allUsers = Model('User')->field('userID,name,nickName')->select();
        $usersByName = array();
        foreach ($allUsers as $user) {
            $usersByName[(string)$user['name']] = $user;
        }

        $credentialLines = array();
        $createdUserCount = 0;
        $reusedUserCount = 0;
        $userIDs = array();
        foreach ($userPlan as $item) {
            list($name, $nickName, $groupName) = $item;
            if (!isset($groupIds[$groupName])) {
                return array('success' => false, 'message' => 'missing user group: ' . $groupName);
            }
            $user = isset($usersByName[$name]) ? $usersByName[$name] : null;
            if (!$user) {
                $plainPassword = $this->randomPassword();
                $userID = Model('User')->userAdd(array(
                    'name' => $name,
                    'nickName' => $nickName,
                    'password' => KodUser::parsePass($plainPassword),
                    'roleID' => 2,
                    'sizeMax' => 0,
                    'email' => '',
                    'phone' => '',
                    'avatar' => '',
                    'sex' => 1,
                    'status' => 1,
                ));
                if ($userID <= 0) {
                    return array('success' => false, 'message' => 'failed to create user: ' . $name);
                }
                $user = array('userID' => $userID, 'name' => $name, 'nickName' => $nickName);
                $usersByName[$name] = $user;
                $credentialLines[] = $name . "\t" . $plainPassword;
                $createdUserCount++;
            } else {
                $reusedUserCount++;
            }
            $userID = intval($user['userID']);
            $userIDs[$name] = $userID;
            $groupInfo = array((string)$groupIds[$groupName] => 1);
            if (Model('User')->userGroupSet($userID, $groupInfo, true) === false) {
                return array('success' => false, 'message' => 'failed to set user group: ' . $name);
            }
        }

        $credentialFile = '';
        if (!empty($credentialLines)) {
            $credentialFile = DATA_PATH . 'system/oaDeptSync-initial-credentials.txt';
            file_put_contents($credentialFile, implode("\n", $credentialLines) . "\n", LOCK_EX);
            @chmod($credentialFile, 0600);
        }

        return array(
            'success' => true,
            'departmentCount' => count($groupPlan),
            'createdDepartmentCount' => $createdGroupCount,
            'reusedDepartmentCount' => $reusedGroupCount,
            'createdSourceCount' => $createdSourceCount,
            'userCount' => count($userPlan),
            'createdUserCount' => $createdUserCount,
            'reusedUserCount' => $reusedUserCount,
            'credentialFile' => $credentialFile,
            'groups' => $groupIds,
            'users' => $userIDs,
        );
    }

    private function randomPassword() {
        return 'K' . substr(bin2hex(random_bytes(12)), 0, 20) . '!';
    }

    private function createDefaultGroupFolders($sourceID) {
        foreach (array('共享资源', '文档', '其他') as $name) {
            IO::mkdir("{source:{$sourceID}}/" . $name);
        }
    }

    public function sync() {
        if (!KodUser::isLogin()) {
            $this->json(false, 'login required');
        }
        KodUser::checkRoot();

        $rootGroupID = trim((string)Input::get('rootGroupId', 'require', '1'));
        $dryRun = Input::get('dryRun', 'require', '1') !== '0';
        $confirmed = Input::get('confirm', 'require', '0') === '1';
        if (!$dryRun && !$confirmed) {
            $this->json(false, 'execution requires confirm=1');
        }

        $groups = $this->loadGroups($rootGroupID);
        if (empty($groups)) {
            $this->json(false, 'no groups found');
        }

        $groupIDs = array_keys($groups);
        $sourceMap = $this->loadGroupSources($groupIDs);
        $createdSourceCount = 0;
        if (!$dryRun) {
            foreach ($groups as $groupID => &$group) {
                if (!isset($sourceMap[$groupID])) {
                    $sourceID = Model('Source')->groupRootAdd($groupID);
                    if (!$sourceID) {
                        $this->json(false, 'failed to create group source: ' . $groupID);
                    }
                    $sourceMap[$groupID] = $sourceID;
                    $createdSourceCount++;
                }
                $this->createDefaultGroupFolders($sourceMap[$groupID]);
                $group['sourceId'] = intval($sourceMap[$groupID]);
            }
            unset($group);
        } else {
            foreach ($groups as $groupID => &$group) {
                $group['sourceId'] = isset($sourceMap[$groupID]) ? intval($sourceMap[$groupID]) : null;
            }
            unset($group);
        }

        $users = $this->loadUserGroups($groupIDs);
        $revokedPermissionCount = $dryRun ? 0 : $this->revokeDirectUserPermissions($groups, $sourceMap);
        $resultGroups = array_values($groups);
        $resultUsers = array_values($users);
        $this->json(true, $dryRun ? 'dry run completed' : 'organization sync completed', array(
            'success' => true,
            'departmentCount' => count($resultGroups),
            'userCount' => count($resultUsers),
            'createdSourceCount' => $createdSourceCount,
            'revokedPermissionCount' => $revokedPermissionCount,
            'message' => $dryRun ? 'dry run completed' : 'organization sync completed',
            'groups' => $resultGroups,
            'users' => $resultUsers,
        ));
    }

    private function loadGroups($rootGroupID) {
        $rows = Model('Group')->field('groupID,name,parentID,sort')->order('sort asc,groupID asc')->select();
        $all = array();
        foreach ($rows as $row) {
            $id = (string)$row['groupID'];
            $all[$id] = array(
                'groupId' => $id,
                'parentGroupId' => (string)$row['parentID'],
                'name' => (string)$row['name'],
                'sort' => intval($row['sort']),
                'status' => $this->groupStatus($id),
                'sourceId' => null,
            );
        }
        if (!$rootGroupID || !isset($all[$rootGroupID])) {
            return array();
        }
        $result = array();
        foreach ($all as $id => $group) {
            if ($this->isUnderRoot($id, $rootGroupID, $all)) {
                $result[$id] = $group;
            }
        }
        return $result;
    }

    private function isUnderRoot($groupID, $rootGroupID, $all) {
        $seen = array();
        $current = $groupID;
        while ($current !== null && $current !== '' && !isset($seen[$current])) {
            if ($current === $rootGroupID) {
                return true;
            }
            $seen[$current] = true;
            if (!isset($all[$current])) {
                return false;
            }
            $parent = (string)$all[$current]['parentGroupId'];
            $current = $parent === '0' ? null : $parent;
        }
        return false;
    }

    private function groupStatus($groupID) {
        $meta = Model('group_meta')->where(array(
            'groupID' => $groupID,
            'key' => 'status',
        ))->field('value')->find();
        return $meta && (string)$meta['value'] === '0' ? 0 : 1;
    }

    private function loadGroupSources($groupIDs) {
        if (empty($groupIDs)) {
            return array();
        }
        $rows = Model('Source')->where(array(
            'targetType' => 2,
            'targetID' => array('in', $groupIDs),
            'parentID' => 0,
            'isDelete' => 0,
        ))->field('sourceID,targetID')->select();
        $result = array();
        foreach ($rows as $row) {
            $result[(string)$row['targetID']] = intval($row['sourceID']);
        }
        return $result;
    }

    private function loadUserGroups($groupIDs) {
        if (empty($groupIDs)) {
            return array();
        }
        $rows = Model('user_group')->where(array(
            'groupID' => array('in', $groupIDs),
        ))->field('userID,groupID')->select();
        $result = array();
        foreach ($rows as $row) {
            $userID = (string)$row['userID'];
            if (!isset($result[$userID])) {
                $result[$userID] = array(
                    'userId' => $userID,
                    'groupIds' => array(),
                );
            }
            $result[$userID]['groupIds'][] = (string)$row['groupID'];
        }
        return $result;
    }

    /**
     * Department access is granted by the group membership. Remove historical
     * direct user grants from the complete department tree so a stale share
     * cannot bypass the organization boundary through a child path.
     */
    private function revokeDirectUserPermissions($groups, $sourceMap) {
        $revoked = 0;
        foreach ($groups as $groupID => $group) {
            if (!isset($sourceMap[$groupID])) {
                continue;
            }
            $sourceIDs = $this->loadSourceTreeIds($sourceMap[$groupID]);
            if (empty($sourceIDs)) {
                continue;
            }
            // Use Kodbox's database adapter for this narrow cleanup. Kodbox
            // versions differ in how the generated SourceAuth ORM expands
            // conditions, while the table contract is stable.
            foreach ($sourceIDs as $sourceID) {
                $sourceID = intval($sourceID);
                $db = Model()->db();
                $rows = $db->query(
                    'select id from io_source_auth where sourceID=' . $sourceID . ' and targetType=1'
                );
                foreach ($rows as $row) {
                    $revoked++;
                }
                $db->execute(
                    'delete from io_source_auth where sourceID=' . $sourceID . ' and targetType=1'
                );
            }
        }
        return $revoked;
    }

    private function loadSourceTreeIds($rootSourceID) {
        $rootSourceID = intval($rootSourceID);
        if ($rootSourceID <= 0) {
            return array();
        }
        $sourceIDs = array($rootSourceID => true);
        $frontier = array($rootSourceID);
        while (!empty($frontier)) {
            $rows = Model('Source')->where(array(
                'parentID' => count($frontier) === 1
                    ? $frontier[0]
                    : array('in', $frontier),
                'isDelete' => 0,
            ))->field('sourceID')->select();
            $next = array();
            foreach ($rows as $row) {
                $sourceID = intval($row['sourceID']);
                if ($sourceID <= 0 || isset($sourceIDs[$sourceID])) {
                    continue;
                }
                $sourceIDs[$sourceID] = true;
                $next[] = $sourceID;
            }
            $frontier = $next;
        }
        return array_map('intval', array_keys($sourceIDs));
    }

    private function json($success, $message, $data = null) {
        $result = array(
            'success' => (bool)$success,
            'message' => $message,
        );
        if (is_array($data)) {
            $result = array_merge($result, $data);
        }
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($result, JSON_UNESCAPED_UNICODE);
        exit;
    }
}
