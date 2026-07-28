import base64
import copy
import json
import sys


ORG_JSON = "/tmp/org.json"
PASSWORD_HASH = "$2y$10$cSTPhfSjIkADdo2495miveBj.u9qHaHbo7LtFltUEn1gpZNTJKtP6"


def hx(value):
    return "0x" + str(value).encode("utf-8").hex()


def sql_text(value):
    return hx(value)


def load_people():
    with open(ORG_JSON, encoding="utf-8") as file:
        return json.load(file)["uniquePeopleList"]


existing_ids = {
    "侯斌超": 215, "钱爱梅": 216, "马倩": 217, "邴燕萍": 218, "张华": 219,
    "张龄": 220, "濮卫民": 221, "李丹": 222, "苏莉": 223, "罗翔": 224,
    "缪云涛": 225, "严己": 226, "何志华": 227, "李豪杰": 228, "朱新捷": 229,
    "赖志勇": 230, "金晨": 231, "曹慧霆": 232, "马书韵": 233, "卜义洁": 234,
    "黄潇仪": 235, "张皑宁": 236, "毛丹": 237, "蔡萌": 238, "郭云": 239,
    "朱艺": 240, "徐佳琪": 241, "盛亦文": 242, "陈洁": 243, "许纯": 244,
    "傅韵同": 245, "金晓辉": 246, "黄俣博": 247, "向悦维": 248, "胡可欣": 249,
    "罗雅": 250, "徐心怡": 251, "黄静荷": 252, "王思齐": 253, "李乐卉": 254,
    "赵莉": 255, "许璇璇": 256, "张坤喆": 257, "李朗荻": 258, "何宏福": 259,
    "张伟丽": 260, "黄丽萍": 261, "张弛": 262, "陶甄宇": 263, "沈昱": 264,
    "张井芳": 265, "王春平": 266, "杨震雷": 267,
}


def make_ids(people):
    result = dict(existing_ids)
    next_id = 268
    for name in people:
        if name not in result:
            result[name] = next_id
            next_id += 1
    return result


def dept_rows():
    # 新树统一挂在现有“规划院”根部门 201 下。
    return [
        (300, "院长", 201, 10, 215),
        (301, "分管领导", 201, 20, None),
        (302, "钱爱梅", 301, 10, 216),
        (303, "邴燕萍", 301, 20, 218),
        (304, "马倩", 301, 30, 217),
        (305, "张华", 301, 40, 219),
        (306, "总师", 201, 30, None),
        (307, "城市更新规划所", 302, 10, 217),
        (308, "城市设计所", 302, 20, 221),
        (309, "总体规划和专项规划所", 302, 30, 218),
        (310, "乡村规划所", 302, 40, 222),
        (311, "规划研究室", 304, 10, 224),
        (312, "数字城市规划所", 304, 20, 217),
        (313, "交通市政规划所", 305, 10, 225),
        (314, "技术审查室", 305, 20, None),
        (315, "综合科", 303, 10, None),
        (316, "综合科", 305, 20, None),
        (317, "行政办公", 315, 10, 223),
        (318, "财务管理", 315, 20, 223),
        (319, "计划经营", 316, 10, 227),
    ]


primary_dept = {
    "侯斌超": 300, "钱爱梅": 302, "邴燕萍": 303, "马倩": 304, "张华": 305,
    "张龄": 306, "朱新捷": 306,
    "张皑宁": 307, "卜义洁": 307, "许纯": 307, "毛丹": 307, "郭云": 307,
    "金晓辉": 307, "李乐卉": 307, "蔡萌": 307, "傅韵同": 307,
    "濮卫民": 308, "薛友谊": 308, "陈凌云": 308, "黄潇仪": 308, "孙瑞敏": 308,
    "刘超": 308, "罗雅": 308, "马书韵": 308, "黄俣博": 308, "李朗荻": 308,
    "吴双": 308, "徐佳琪": 308, "盛亦文": 308,
    "张坤喆": 309, "陈洁": 309, "李春晖": 309, "黄静荷": 309, "朱艺": 309,
    "许璇璇": 309, "王春平": 309, "张井芳": 309,
    "李丹": 310, "王思齐": 310, "徐海玲": 310, "向悦维": 310, "胡可欣": 310,
    "徐心怡": 310,
    "罗翔": 311, "曹慧霆": 311,
    "黄丽萍": 312, "金晨": 312,
    "缪云涛": 313, "张弛": 313, "沈昱": 313, "张亦慧": 313, "赵莉": 313,
    "陶甄宇": 313, "何宏福": 313, "张伟丽": 313, "杨震雷": 313,
    "严己": 314, "赖志勇": 314,
    "苏莉": 317, "黄华": 317, "顾俊": 317, "徐鑫赟": 317,
    "何志华": 319, "李豪杰": 319, "翁培峰": 318, "蒋欣怡": 318,
}


post_by_name = {
    "侯斌超": 18,
    "钱爱梅": 19, "邴燕萍": 19, "马倩": 19,
    "张华": 20, "张龄": 20, "朱新捷": 20,
    "濮卫民": 21, "李丹": 21, "苏莉": 21, "罗翔": 21, "缪云涛": 21,
    "何志华": 22,
}


def sql_org(people, ids):
    lines = ["SET NAMES utf8mb4;", "START TRANSACTION;"]
    old_ids = ",".join(str(i) for i in range(202, 222))
    lines.append(f"UPDATE system_dept SET deleted=1,status=1,leader_user_id=NULL WHERE id IN ({old_ids});")
    for dept_id, name, parent_id, sort, leader_id in dept_rows():
        leader = "NULL" if leader_id is None else str(leader_id)
        lines.append(
            "INSERT INTO system_dept(id,name,parent_id,sort,leader_user_id,status,deleted,tenant_id,creator,create_time,updater,update_time) "
            f"VALUES({dept_id},{sql_text(name)},{parent_id},{sort},{leader},0,0,1,'admin',NOW(),'admin',NOW()) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name),parent_id=VALUES(parent_id),sort=VALUES(sort),leader_user_id=VALUES(leader_user_id),status=0,deleted=0,tenant_id=1,updater='admin',update_time=NOW();"
        )
    for name in people:
        if name not in primary_dept:
            raise RuntimeError(f"未配置主部门：{name}")
        if name not in existing_ids:
            uid = ids[name]
            lines.append(
                "INSERT IGNORE INTO system_users(id,username,password,nickname,dept_id,post_ids,status,creator,create_time,updater,update_time,deleted,tenant_id) "
                f"VALUES({uid},{sql_text(name)},{sql_text(PASSWORD_HASH)},{sql_text(name)},{primary_dept[name]},{sql_text('[]')},0,'admin',NOW(),'admin',NOW(),0,1);"
            )
        post_id = post_by_name.get(name)
        post_ids = "[" + str(post_id) + "]" if post_id else "[]"
        lines.append(
            f"UPDATE system_users SET nickname={sql_text(name)},dept_id={primary_dept[name]},post_ids={sql_text(post_ids)},status=0,deleted=0,tenant_id=1,updater='admin',update_time=NOW() WHERE username={sql_text(name)};"
        )
    user_ids = ",".join(str(ids[name]) for name in people)
    lines.append(f"UPDATE system_user_role SET deleted=1,updater='admin',update_time=NOW() WHERE tenant_id=1 AND user_id IN ({user_ids});")
    lines.append(f"UPDATE system_user_post SET deleted=1,updater='admin',update_time=NOW() WHERE tenant_id=1 AND user_id IN ({user_ids});")
    for name in people:
        uid = ids[name]
        lines.append(f"INSERT INTO system_user_role(user_id,role_id,creator,create_time,tenant_id,deleted) VALUES({uid},2,'admin',NOW(),1,0);")
        if name in ("曹慧霆", "金晨"):
            lines.append(f"INSERT INTO system_user_role(user_id,role_id,creator,create_time,tenant_id,deleted) VALUES({uid},3,'admin',NOW(),1,0);")
        if name in post_by_name:
            lines.append(f"INSERT INTO system_user_post(user_id,post_id,creator,create_time,tenant_id,deleted) VALUES({uid},{post_by_name[name]},'admin',NOW(),1,0);")
    return lines


def condition_setting(user_ids):
    return {
        "conditionType": 2,
        "conditionExpression": None,
        "defaultFlow": False,
        "conditionGroups": {
            "and": False,
            "conditions": [
                {"and": True, "rules": [{"opCode": "==", "leftSide": "PROCESS_START_USER_ID", "rightSide": str(uid)}]}
                for uid in user_ids
            ],
        },
    }


def activity(template, node_id, name, user_id=None, self_select=False):
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["type"] = 11
    node["name"] = name
    node["showText"] = "发起人自选（张华/张龄/朱新捷三选一）" if self_select else f"指定成员：{name}"
    node["candidateStrategy"] = 35 if self_select else 30
    node["candidateParam"] = "" if self_select else str(user_id)
    node["approveType"] = 1
    node["approveMethod"] = 3
    node.pop("childNode", None)
    for key in ("fieldsPermission", "buttonsSetting", "signEnable", "reasonRequire", "skipExpression",
                "rejectHandler", "timeoutHandler", "assignStartUserHandlerType", "assignEmptyHandler",
                "taskCreateListener", "taskAssignListener", "taskCompleteListener"):
        node.pop(key, None)
    return node


def strategy_activity(template, node_id, name, strategy, param, show_text):
    node = copy.deepcopy(template)
    node["id"] = node_id
    node["type"] = 11
    node["name"] = name
    node["showText"] = show_text
    node["candidateStrategy"] = strategy
    node["candidateParam"] = str(param)
    node["approveType"] = 1
    node["approveMethod"] = 3
    node.pop("childNode", None)
    for key in ("fieldsPermission", "buttonsSetting", "signEnable", "reasonRequire", "skipExpression",
                "rejectHandler", "timeoutHandler", "assignStartUserHandlerType", "assignEmptyHandler",
                "taskCreateListener", "taskAssignListener", "taskCompleteListener"):
        node.pop(key, None)
    return node


def branch(template, flow_id, title, start_ids, chain):
    first = None
    previous = None
    for index, item in enumerate(chain):
        if item[0] == "self":
            node = activity(template, f"Activity_{flow_id}_{index}", "严己自选审批人", self_select=True)
        else:
            node = activity(template, f"Activity_{flow_id}_{index}", item[0], item[1])
        if first is None:
            first = node
        if previous is not None:
            previous["childNode"] = node
        previous = node
    return {
        "id": f"Flow_{flow_id}",
        "type": 50,
        "name": title,
        "showText": title,
        "childNode": first,
        "conditionSetting": condition_setting(start_ids),
    }


def find_gateway(node):
    if isinstance(node, dict):
        if node.get("type") == 51:
            return node
        found = find_gateway(node.get("childNode"))
        if found:
            return found
        for item in node.get("conditionNodes", []) if isinstance(node.get("conditionNodes"), list) else []:
            found = find_gateway(item)
            if found:
                return found
    return None


def update_model(model, ids):
    gateway = find_gateway(model)
    if not gateway:
        raise RuntimeError("审批模型中未找到分流网关")
    old_conditions = gateway.get("conditionNodes", [])
    default_branch = next((x for x in old_conditions if x.get("conditionSetting", {}).get("defaultFlow") is True or "其它人员" in x.get("showText", "")), None)
    if default_branch is None:
        default_branch = {
            "id": "Flow_default",
            "type": 50,
            "name": "默认部门负责人后院长",
            "showText": "其它人员：部门负责人后到院长",
            "childNode": activity(next(n for n in old_conditions[0].get("childNode", {}).get("childNode", {}).values() if False), "Activity_default_0", "部门负责人审批", 0),
            "conditionSetting": {"conditionType": None, "conditionExpression": None, "defaultFlow": True, "conditionGroups": None},
        }
    task_template = None
    def locate_task(n):
        nonlocal task_template
        if task_template is not None or not isinstance(n, dict):
            return
        if n.get("type") == 11 and "fieldsPermission" in n:
            task_template = n
            return
        locate_task(n.get("childNode"))
        for child in n.get("conditionNodes", []) if isinstance(n.get("conditionNodes"), list) else []:
            locate_task(child)
    locate_task(model)
    if task_template is None:
        raise RuntimeError("审批模型中未找到审批节点模板")

    def uid(name):
        return ids[name]

    branches = []
    branches.append(branch(task_template, "tech-direct", "技术审查室：张华/张龄/朱新捷直达侯斌超", [uid("张华"), uid("张龄"), uid("朱新捷")], [("侯斌超", uid("侯斌超"))]))
    branches.append(branch(task_template, "tech-self", "技术审查室：严己自己点选", [uid("严己")], [("self", None)]))
    branches.append(branch(task_template, "tech-lai", "技术审查室：赖志勇到朱新捷", [uid("赖志勇")], [("朱新捷", uid("朱新捷"))]))
    branches.append(branch(task_template, "plan-member", "计划经营：李豪杰到何志华再到张华", [uid("李豪杰")], [("何志华", uid("何志华")), ("张华", uid("张华"))]))
    branches.append(branch(task_template, "plan-leader", "计划经营负责人：何志华到张华", [uid("何志华")], [("张华", uid("张华"))]))
    branches.append(branch(task_template, "admin-finance-members", "行政办公/财务：苏莉到邴燕萍再到侯斌超", [uid(x) for x in ["黄华", "顾俊", "徐鑫赟", "翁培峰", "蒋欣怡"]], [("苏莉", uid("苏莉")), ("邴燕萍", uid("邴燕萍")), ("侯斌超", uid("侯斌超"))]))
    branches.append(branch(task_template, "admin-leader", "行政办公/财务负责人：邴燕萍到侯斌超", [uid("苏莉")], [("邴燕萍", uid("邴燕萍")), ("侯斌超", uid("侯斌超"))]))
    branches.append(branch(task_template, "digital-members", "数字城市规划所：马倩到侯斌超", [uid("黄丽萍"), uid("金晨")], [("马倩", uid("马倩")), ("侯斌超", uid("侯斌超"))]))

    ordinary_members = [
        "张皑宁", "卜义洁", "许纯", "毛丹", "郭云", "金晓辉", "李乐卉", "蔡萌", "傅韵同",
        "薛友谊", "陈凌云", "黄潇仪", "孙瑞敏", "刘超", "罗雅", "马书韵", "黄俣博", "李朗荻", "吴双", "徐佳琪", "盛亦文",
        "张坤喆", "陈洁", "李春晖", "黄静荷", "朱艺", "许璇璇", "王春平", "张井芳",
        "王思齐", "徐海玲", "向悦维", "胡可欣", "徐心怡", "曹慧霆",
        "张弛", "沈昱", "张亦慧", "赵莉", "陶甄宇", "何宏福", "张伟丽", "杨震雷",
    ]
    # 普通所成员：第一级为本部门负责人，第二级为父部门负责人，最后到院长。
    ordinary_branch = {
        "id": "Flow_ordinary-members",
        "type": 50,
        "name": "普通所：部门负责人再到上级分管领导最后到侯斌超",
        "showText": "普通所：部门负责人再到上级分管领导最后到侯斌超",
        "childNode": strategy_activity(task_template, "Activity_ordinary-members_0", "发起人部门负责人", 37, 1, "发起人部门负责人"),
        "conditionSetting": condition_setting([uid(x) for x in ordinary_members]),
    }
    ordinary_branch["childNode"]["childNode"] = strategy_activity(task_template, "Activity_ordinary-members_1", "发起人上级部门负责人", 37, 2, "发起人上级部门负责人")
    ordinary_branch["childNode"]["childNode"]["childNode"] = activity(task_template, "Activity_ordinary-members_2", "侯斌超", uid("侯斌超"))
    branches.append(ordinary_branch)
    leader_branch = {
        "id": "Flow_ordinary-leaders",
        "type": 50,
        "name": "普通所负责人：上级分管领导再到侯斌超",
        "showText": "普通所负责人：上级分管领导再到侯斌超",
        "childNode": strategy_activity(task_template, "Activity_ordinary-leaders_0", "发起人上级部门负责人", 37, 2, "发起人上级部门负责人"),
        "conditionSetting": condition_setting([uid(x) for x in ["濮卫民", "李丹", "罗翔", "缪云涛"]]),
    }
    leader_branch["childNode"]["childNode"] = activity(task_template, "Activity_ordinary-leaders_1", "侯斌超", uid("侯斌超"))
    branches.append(leader_branch)
    branches.append(branch(task_template, "leader-direct", "分管领导：直接到侯斌超", [uid(x) for x in ["钱爱梅", "邴燕萍", "马倩", "张华"]], [("侯斌超", uid("侯斌超"))]))
    # 仅保留原有默认分支；它继续服务于规划院之外的账号。
    gateway["conditionNodes"] = branches + [default_branch]
    return model


def sql_models(rows, ids):
    lines = []
    for line in rows:
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) != 3:
            continue
        info_id, code, encoded = parts
        if code == "tpl:oa_leave_test":
            continue
        model = json.loads(base64.b64decode(encoded.replace("\\n", "").replace("\\r", "")).decode("utf-8"))
        updated = update_model(model, ids)
        payload = json.dumps(updated, ensure_ascii=False, separators=(",", ":")).encode("utf-8").hex()
        lines.append(f"UPDATE bpm_process_definition_info SET simple_model=0x{payload},updater='admin',update_time=NOW() WHERE id={info_id} AND deleted=0;")
    return lines


def main():
    people = load_people()
    ids = make_ids(people)
    all_lines = sql_org(people, ids)
    model_rows = sys.stdin.readlines()
    all_lines.extend(sql_models(model_rows, ids))
    all_lines.append("COMMIT;")
    print("\n".join(all_lines))
    print(f"-- PERSON_COUNT={len(people)}", file=sys.stderr)
    print(f"-- MODEL_UPDATE_COUNT={sum(1 for line in all_lines if line.startswith('UPDATE bpm_process_definition_info'))}", file=sys.stderr)
    print("-- NEW_USER_IDS=" + json.dumps({k: v for k, v in ids.items() if v >= 268}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
