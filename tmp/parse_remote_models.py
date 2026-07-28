import sys, base64, json

for line in sys.stdin:
    parts = line.rstrip("\n").split("\t", 2)
    if len(parts) != 3:
        continue
    try:
        encoded = parts[2].replace("\\n", "").replace("\\r", "")
        obj = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except Exception as exc:
        print("DECODE_ERROR", parts[:2], repr(exc))
        continue
    nodes = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") in (11, 13, 30, 50):
            nodes.append({key: node.get(key) for key in ("id", "type", "name", "showText", "candidateStrategy", "candidateParam", "approveType", "approveMethod")})
        walk(node.get("childNode"))
        for branch in node.get("branchs", []) if isinstance(node.get("branchs"), list) else []:
            walk(branch)
        for child in node.get("conditionNodes", []) if isinstance(node.get("conditionNodes"), list) else []:
            walk(child)

    walk(obj)
    print("TEMPLATE", parts[0], parts[1], "nodes", len(nodes))
    for node in nodes:
        print(json.dumps(node, ensure_ascii=False))
