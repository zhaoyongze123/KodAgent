---
name: approvals
skill_id: approval.operations
capability_id: approval_read, approval_write, approval_process
version: 1.0.0
description: 审批查询、申请、单条处理、批量处理和撤回的领域语义与澄清策略。
---

# 审批领域 Skill

具体 action_id 必须从当前 route_conversation 工具 schema 的 enum 选择；本 Skill 不定义动作名称。

## 意图边界

- “我的待办”“有哪些审批要处理”属于待办查询。
- “我发起的审批”与“已办历史”是不同查询范围，不能混用。
- “发起审批”属于申请草稿；“通过/驳回”属于待办动作；“撤回”只针对本人仍在运行的流程。
- “批量通过/批量驳回”是批量动作，不能拆成多个无关的单条动作。

## 澄清策略

- 查询范围、流程编号、任务编号或动作理由缺失时先澄清。
- 申请、单条处理、批量处理和撤回都必须保留待确认状态，不能把预览或草稿说成已提交。
- 已结束、无权限或来源不唯一时如实返回业务结果，不猜测流程事实。
