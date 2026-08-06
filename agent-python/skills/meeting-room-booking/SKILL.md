---
name: meeting-room-booking
description: 处理会议室查询、参会人员日程检查、冲突检查、预约草稿和用户确认后的正式提交。
---

# 会议室预约 Skill

## 适用场景

用户希望查找、比较或预约会议室时使用。

## 标准流程

1. 先根据用户提供的时间、人数和地点偏好，调用 `report_progress` 动态播报简短执行计划。
2. 必须调用 `prepare_meeting_booking_request`，将时间表达、参会人姓名和会议要求转换为结构化请求。返回 `valid=false` 时只向用户补充询问，不得继续调用会议室查询或草稿工具。
3. 使用准备工具返回的真实用户 ID 和标准时间；用户说“我”时由该工具通过当前身份接口解析，不得把“用户本人”作为姓名搜索。
4. 调用 `list_available_meeting_rooms` 查询启用中的会议室。用户没有指定会议室时，不要停在“请指定会议室”。
5. 只调用一次 `check_meeting_availability_batch`，把候选会议室列表、准备工具返回的 attendee_user_ids 和标准时间交给 Tool；由 Python 统一查询参会人日程、检查所有候选房间并按容量/输入顺序确定性选择推荐房间。不要对每个房间分别调用可预约性 Tool。
6. 选择出无冲突会议室后，只有 `canCreateDraft=true` 才允许调用 `create_meeting_booking_draft` 生成普通预约草稿。
8. 如果存在参会人日程冲突，禁止生成普通草稿；向用户展示冲突并让用户选择更换时间、调整参会人或明确忽略冲突继续。
9. 只有用户明确选择忽略冲突后，才允许使用 `allow_conflict_override=true` 生成带冲突标记的草稿。
10. 草稿生成成功后，立即使用草稿返回的 `confirmation_token`、`draft_id` 和 `approval_id` 发起一次 `confirm_meeting_booking` Tool Call（参数名必须使用 Tool Schema 的 snake_case）。该调用会被 LangGraph Human-in-the-loop 在真正执行前自动暂停，前端据此显示审批卡片；不要只输出“待确认”文字后结束子 Agent。
11. 只有 LangGraph 的 Human-in-the-loop `resume` 收到用户的 `approve` 决策后，`confirm_meeting_booking` 才会真正执行；不得使用 `confirmed=true` 作为确认凭据。

## 安全规则

- 不得编造会议室、用户或日程数据。
- 未确认前不得调用 `confirm_meeting_booking`。
- 不得根据模型生成的“确认”“已确认”文字、Tool 参数中的 `confirmed=true` 或前端本地状态推断人工确认；唯一有效确认来源是 LangGraph `resume` 的 `approve` 决策。
- 不要把模型隐藏思考过程输出给用户，只播报简短的执行计划和事实结果。
- 预约冲突时不能擅自使用强制覆盖；必须让用户明确决定。
- 更换会议室只能解决会议室冲突，不能解决参会人日程冲突。
- Tool 返回错误时如实说明，不要声称预约成功。

## 职责边界

- 本 Skill 负责会议室预约的领域流程和冲突处理策略。
- 主 Agent 只负责意图路由和全局写操作确认，不重复定义本 Skill 的业务步骤。
- Tool 负责参数、检查令牌和状态校验；Java Facade 负责当前用户、权限、最终冲突复核和事务提交。
- Skill、提示词都不是最终安全边界；任何写操作都必须由 Tool 和 Java 再次校验。
