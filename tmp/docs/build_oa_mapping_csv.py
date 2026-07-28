import csv
from pathlib import Path

from build_oa_process_mapping import classify, parse_rows


OUT = Path('/Users/mac/项目/若伊部署/output/csv/规划院OA用户与审批流程映射表-20260710.csv')
OUT.parent.mkdir(parents=True, exist_ok=True)


def step_count(approvers, flow_type):
    if '多部门' in flow_type:
        return '多路线'
    if not approvers or approvers.startswith('不纳入') or '无需' in approvers:
        return 0
    if '→' in approvers:
        return len(approvers.split('→'))
    return 1 if '侯斌超' in approvers else 0


def action_for(flow_type, name):
    if '非OA业务账号' in flow_type:
        return '不作为规划院OA流程发起人；如需验证登录或权限，单独测试'
    if '院长' in flow_type or '所长/分管领导' in flow_type or '总师' in flow_type:
        return '保留可道云账号；作为审批节点登录后人工审批'
    return '流程完成且无报错后可删除本次发起人，再创建下一名用户；审批节点账号保留'


def main():
    headers = [
        '序号', '可道云用户', '可道云角色', '原始所在部门', '归属所/部门',
        '测试分类', '审批经过人员（不含发起人）', '审批节点数', '账号处理建议', '证据/备注'
    ]
    rows = []
    for rec in parse_rows():
        flow_type, unit, approvers, note = classify(rec)
        rows.append([
            rec['id'],
            rec['name'],
            rec['role'],
            '；'.join(rec['depts']),
            unit,
            flow_type,
            approvers,
            step_count(approvers, flow_type),
            action_for(flow_type, rec['name']),
            note,
        ])
    with OUT.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(OUT)
    print('data_rows=', len(rows))


if __name__ == '__main__':
    main()
