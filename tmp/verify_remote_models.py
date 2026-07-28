import base64
import json
import sys


def gateway(node):
    if not isinstance(node, dict):
        return None
    if node.get("type") == 51:
        return node
    found = gateway(node.get("childNode"))
    if found:
        return found
    for item in node.get("conditionNodes", []) if isinstance(node.get("conditionNodes"), list) else []:
        found = gateway(item)
        if found:
            return found
    return None


def terminals(node):
    if not isinstance(node, dict):
        return []
    if node.get("type") == 11:
        child = node.get("childNode")
        if child:
            return terminals(child)
        return [node.get("showText")]
    return terminals(node.get("childNode"))


for line in sys.stdin:
    parts = line.rstrip("\n").split("\t", 2)
    if len(parts) != 3:
        continue
    info_id, code, encoded = parts
    obj = json.loads(base64.b64decode(encoded.replace("\\n", "").replace("\\r", "")).decode("utf-8"))
    gate = gateway(obj)
    if not gate:
        print(f"{info_id}\t{code}\tNO_GATEWAY")
        continue
    nodes = gate.get("conditionNodes", [])
    print(f"{info_id}\t{code}\tbranches={len(nodes)}")
    for node in nodes:
        setting = node.get("conditionSetting", {})
        ids = []
        groups = setting.get("conditionGroups") or {}
        for condition in groups.get("conditions", []) if isinstance(groups, dict) else []:
            for rule in condition.get("rules", []):
                if rule.get("leftSide") == "PROCESS_START_USER_ID":
                    ids.append(rule.get("rightSide"))
        print("  ", node.get("name"), "start_ids=" + ",".join(ids), "terminal=" + " -> ".join(terminals(node.get("childNode"))))
