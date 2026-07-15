# Agent Replan 修复开发方案

## 1. 文档目的

本文档用于将当前 Agent Runtime 从“只读 Tool-Calling 循环 + 会议冲突确定性恢复”升级为“受约束、可审计、可恢复的 Agent Replan”。

本方案只调整 Agent Runtime、Action 协议、权限策略和通用 Runtime UI Schema，不在 Dify Chatflow 中增加会议、日程或审批领域分支。

第一期验收目标保持克制：

```text
创建会议发生会议室冲突
→ 冲突写入结构化 Observation
→ Planner 在受限工具集中重新规划
→ 查询原时间范围内的真实可用会议室
→ 生成 1 至 3 个可验证候选方案
→ 用户选择候选方案
→ 用户确认写操作
→ OA Service 最终校验并创建会议
```

第一期不自动修改会议时间，不自动放宽容量或设备要求，不允许跳过用户确认。

---

## 2. 当前实现基线

### 2.1 已实现能力

当前代码已经具备以下基础：

- `RuntimeToolCallingAgentPlanner` 可以从 Action Registry 动态生成 Tool Catalog。
- 只读 Action 可以在同一个 Run 中连续执行。
- Run 中保存 `stepCount`、`executedToolKeys` 和 `observations`。
- 写 Action 根据 `confirmationRequired` 进入 `WAITING_CONFIRMATION`。
- `meeting.availability.search` 可以查询指定时间范围内的真实空闲会议室。
- `meeting.candidate.rank` 可以对候选会议室进行确定性排序。
- 会议冲突可以转换成 `MEETING_ROOM_CONFLICT`。
- Runtime UI 可以展示候选方案按钮，用户选择后进入二次确认。
- OA Service 在最终创建时重新执行会议室冲突校验。

### 2.2 当前核心缺口

当前冲突恢复链路为：

```text
meeting.create 抛出冲突
→ Runtime 固定调用 meeting.availability.search
→ Runtime 固定调用 meeting.candidate.rank
→ WAITING_RECOVERY
→ 用户选择数组下标
→ WAITING_CONFIRMATION
```

该链路实现了自动候选效果，但不属于真正的 Agent Replan，原因如下：

1. 冲突没有追加到通用 `observations`，而是单独保存为 `lastError`。
2. 冲突后没有重新进入统一 Planner 循环。
3. Runtime 写死了下一步工具，LLM 没有在受限工具集内重新决策。
4. 自动查询候选的两次 Action 没有形成独立 Step，也没有走统一去重、权限和审计逻辑。
5. 候选方案只是错误详情中的 `List<Map<String, Object>>`，缺少稳定标识、版本和过期时间。
6. 恢复参数会无白名单合并到写操作参数，存在控制字段注入风险。
7. Action 只有认证和确认控制，缺少统一权限策略。
8. 确认记录设置了过期时间，但执行时没有校验。

---

## 3. 目标架构

### 3.1 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| LLM Planner | 根据目标、约束和 Observation 选择下一步 Action | 判断资源真实可用性、绕过权限、宣布写操作成功 |
| Runtime | 状态机、预算、白名单、参数校验、权限、确认、幂等、审计、恢复 | 复制 OA 领域业务规则 |
| Action Handler | 参数适配、调用 OA Service、返回结构化结果 | 自行维护对话状态 |
| OA Service | 权限归属、业务校验、冲突校验、事务、最终数据写入 | Agent 规划和 UI 展示 |
| Dify | 聊天入口、流式消息、Human Input 暂停与恢复 | 会议领域分支和业务规则判断 |
| Runtime UI | 按通用 Schema 展示 Plan、候选、确认和错误 | 信任前端提交的业务参数 |

### 3.2 目标运行链路

```text
用户目标
→ Planner 选择 Action
→ Policy Gate 校验 Action、权限、参数和状态迁移
→ 执行只读 Action
→ 写入 Observation
→ Planner 根据最新 Observation 再规划
→ 得到候选 Plan
→ WAITING_PLAN_CONFIRMATION
→ 用户选择 candidateId
→ 固化 Plan 版本
→ WAITING_CONFIRMATION
→ 用户确认写 Action
→ OA Service 最终校验
→ 成功则 GOAL_COMPLETED
→ 冲突则写入新 Observation 并再次 Replan
```

---

## 4. 状态机改造

### 4.1 推荐状态

保留现有状态并增加 Plan 语义：

| 状态 | 含义 |
|---|---|
| `CREATED` | Run 已创建，尚未规划 |
| `RUNNING` | Planner 或只读 Action 正在执行 |
| `WAITING_INPUT` | 缺少用户必须提供的约束 |
| `WAITING_PLAN_CONFIRMATION` | 已生成候选 Plan，等待用户选择 |
| `WAITING_CONFIRMATION` | 写操作参数已经固化，等待最终确认 |
| `COMPLETED` | OA 业务结果已经证明目标完成 |
| `FAILED` | 不可恢复错误或预算耗尽 |
| `CANCELLED` | 用户取消 |

迁移期可以暂时保留 `WAITING_RECOVERY`，但新的会议冲突流程不再进入该状态。待所有恢复动作迁移到 Plan 协议后删除会议专用 `recover()`。

### 4.2 合法状态迁移

```text
CREATED → RUNNING
RUNNING → RUNNING
RUNNING → WAITING_INPUT
RUNNING → WAITING_PLAN_CONFIRMATION
RUNNING → WAITING_CONFIRMATION
RUNNING → COMPLETED
RUNNING → FAILED

WAITING_INPUT → RUNNING
WAITING_PLAN_CONFIRMATION → WAITING_CONFIRMATION
WAITING_PLAN_CONFIRMATION → RUNNING
WAITING_CONFIRMATION → RUNNING
WAITING_CONFIRMATION → COMPLETED

任意非终态 → CANCELLED
```

Runtime 必须拒绝未声明的状态迁移，不能依赖 Controller 或 Dify 保证调用顺序。

---

## 5. Observation 协议

### 5.1 统一 Observation 模型

新增 `AgentObservation`：

```java
@Data
public class AgentObservation {
    private String observationId;
    private String type;
    private Integer stepNo;
    private String actionId;
    private String outcome;
    private Map<String, Object> requested;
    private Map<String, Object> data;
    private AgentObservationError error;
    private List<String> nextAllowedActions;
    private LocalDateTime occurredAt;
}
```

`type` 推荐值：

- `TOOL_RESULT`
- `ACTION_SUCCEEDED`
- `ACTION_FAILED`
- `HUMAN_INPUT`
- `PLAN_SELECTED`
- `POLICY_REJECTED`
- `BUDGET_EXHAUSTED`

`outcome` 推荐值：

- `SUCCESS`
- `BUSINESS_CONFLICT`
- `VALIDATION_ERROR`
- `PERMISSION_DENIED`
- `TRANSIENT_ERROR`
- `FATAL_ERROR`

### 5.2 会议冲突 Observation

```json
{
  "observationId": "obs-0004",
  "type": "ACTION_FAILED",
  "stepNo": 4,
  "actionId": "meeting.create",
  "outcome": "BUSINESS_CONFLICT",
  "requested": {
    "meetingRoomId": 1,
    "startTime": "2026-07-16 14:00:00",
    "endTime": "2026-07-16 16:00:00"
  },
  "error": {
    "code": "MEETING_ROOM_CONFLICT",
    "message": "1 号会议室在指定时段已被占用",
    "retryable": false,
    "replanRequired": true
  },
  "nextAllowedActions": [
    "meeting.availability.search",
    "meeting.conflict.detail",
    "agent.request_input"
  ]
}
```

冲突会议详情默认不返回会议主题、申请人或完整备注。Planner 只需要知道占用区间和不可用事实。只有具备会议详情权限的用户主动请求查看时，才允许返回脱敏摘要。

### 5.3 持久化要求

第一期可以继续把 Observation 列表存放在 `agent_run.context_json`，但必须满足：

- 新 Observation 只追加，不覆盖历史 Observation。
- 写入前生成稳定 `observationId`。
- 单个 Observation 设置大小上限。
- Tool 返回大列表时只保存摘要和候选引用。
- 进入确认、冲突或完成状态时不得重建空 Context。

生产化阶段建议新增 `agent_observation` 表，避免 Run JSON 无限增长。

---

## 6. Planner 上下文与动态工具白名单

### 6.1 Planner 输入

Planner 每次只接收完成决策所需的安全上下文：

```json
{
  "goal": "安排项目评审会议",
  "constraints": {},
  "currentPlan": {},
  "recentObservations": [],
  "budget": {
    "remainingSteps": 3,
    "remainingTokens": 6000,
    "remainingTimeMs": 18000
  },
  "allowedActions": []
}
```

禁止把以下数据发送给模型：

- API Key、身份票据和 OA Token。
- 未脱敏的其他用户日程内容。
- Runtime 内部幂等键和数据库锁信息。
- 可绕过业务规则的内部控制字段。

### 6.2 动态 Action Catalog

新增：

```java
public interface AgentActionPolicyService {
    List<AgentActionMetadata> listAllowedActions(AgentPlannerContext context);
    void validateBeforeExecution(AgentPlannerContext context,
                                 AgentActionMetadata metadata,
                                 Map<String, Object> arguments);
}
```

`RuntimeToolCallingAgentPlanner` 不再调用 `actionRegistry.listMetadata()`，而是调用 `policyService.listAllowedActions(context)`。

会议冲突第一期允许：

```text
meeting.availability.search
meeting.conflict.detail
meeting.candidate.rank
agent.request_input
```

在候选方案尚未形成前，不向模型暴露 `meeting.create`。候选选择并固化后，写操作由 Runtime 根据 Plan 执行，不允许模型重新拼接写参数。

---

## 7. 参数安全与 Action Policy Gate

### 7.1 服务端 Schema 校验

模型遵守 JSON Schema 不能代替 Runtime 校验。新增 `AgentActionArgumentValidator`：

```java
public interface AgentActionArgumentValidator {
    Map<String, Object> validateAndNormalize(AgentActionMetadata metadata,
                                             Map<String, Object> rawArguments);
}
```

必须实现：

- 删除或拒绝 `additionalProperties`。
- 校验必填字段。
- 校验类型、字符串长度、数组长度和数值范围。
- 时间统一规范化为 `yyyy-MM-dd HH:mm:ss`。
- 用户编号、会议室编号统一转换为 Long。
- 对 Map Key 排序后生成规范化去重键。

### 7.2 禁止控制字段注入

以下字段不得从 LLM、Dify 或前端输入进入会议写操作：

- `forceConflict`
- `applicantUserId`
- `tenantId`
- `status`
- `creator`
- `updater`

`MeetingCreateActionHandler.toRequest()` 必须显式执行：

```java
req.setForceConflict(false);
```

不能读取 `arguments.get("forceConflict")`。

### 7.3 恢复输入白名单

删除通用 `merge(arguments, inputs)`。按交互动作只提取允许字段：

```text
change_room → meetingRoomId
change_time → startTime、endTime
constraint.add → Runtime 声明的 constraint keys
candidate.select → candidateId、planVersion
```

即使前端提交其他字段，Runtime 也必须忽略并记录 `POLICY_REJECTED` 审计事件。

### 7.4 权限策略

Action Metadata 增加：

```java
private String requiredPermission;
private String dataScope;
```

示例：

| Action | 权限 | 数据范围 |
|---|---|---|
| `meeting.availability.search` | `system:meeting-booking:query` | 当前租户会议室 |
| `meeting.conflict.detail` | `system:meeting-booking:query` | 脱敏摘要 |
| `meeting.create` | `system:meeting-booking:create` | 当前用户作为申请人 |
| `meeting.update` | `system:meeting-booking:update` | 仅本人会议 |
| `meeting.cancel` | `system:meeting-booking:update` | 仅本人会议 |

权限校验必须在 Action 执行前完成，不能只依赖 Controller 注解。

---

## 8. ReplanGuard

### 8.1 目的

`409 Conflict` 不允许按原参数重试。Runtime 必须证明新方案改变了导致冲突的约束。

新增：

```java
public interface AgentReplanGuard {
    ReplanValidationResult validate(AgentPlan previousPlan,
                                    AgentObservation conflict,
                                    AgentPlan nextPlan);
}
```

### 8.2 会议冲突规则

第一期规则：

1. `meetingRoomId` 必须与冲突请求不同。
2. `startTime`、`endTime` 必须保持不变。
3. 新会议室必须来自 `meeting.availability.search` 的真实结果。
4. 候选查询时间必须与冲突请求完全一致。
5. 候选必须满足会议人数对应的最小容量。
6. 相同 `meeting.create` 规范化参数不得再次执行。
7. 候选生成后超过有效期必须重新查询。

未来开放自动调整时间时，再增加：

- 时间改变时必须重新执行会议室可用性校验。
- 有参会人时必须重新执行 FreeBusy 查询。
- 不得自动突破用户声明的最晚结束时间等硬约束。

---

## 9. Plan 与 Candidate 模型

### 9.1 AgentPlan

```java
@Data
public class AgentPlan {
    private String planId;
    private Integer version;
    private String goalType;
    private String status;
    private List<String> sourceObservationIds;
    private Map<String, Object> constraints;
    private List<AgentPlanCandidate> candidates;
    private LocalDateTime expiresAt;
}
```

### 9.2 AgentPlanCandidate

```java
@Data
public class AgentPlanCandidate {
    private String candidateId;
    private String actionId;
    private Map<String, Object> arguments;
    private List<String> verifiedByObservationIds;
    private Integer score;
    private List<String> scoreReasons;
    private LocalDateTime expiresAt;
}
```

### 9.3 候选确认协议

前端只提交：

```json
{
  "actionId": "plan.select",
  "inputs": {
    "planId": "plan-2",
    "planVersion": 2,
    "candidateId": "candidate-A"
  }
}
```

Runtime 根据持久化 Plan 读取完整 Action 参数。禁止使用数组下标，禁止接受前端回传的会议室、时间、申请人或其他业务字段。

### 9.4 候选排序规则

第一期确定性评分：

```text
满足硬约束是候选进入列表的前提

容量浪费越少，得分越高
同楼层或同区域，得分更高
用户明确偏好会议室，得分更高
会议室编号仅作为最终稳定排序键
```

排序结果必须返回原因，例如：

```json
{
  "score": 92,
  "scoreReasons": ["容量满足且余量最小", "与原会议室同楼层"]
}
```

---

## 10. Tool-Calling 循环改造

### 10.1 统一循环伪代码

```java
while (run.isRunnable()) {
    budgetService.assertAvailable(run);

    AgentPlannerContext context = contextFactory.build(run);
    List<AgentActionMetadata> allowedActions = policyService.listAllowedActions(context);
    AgentDecision decision = planner.plan(context, allowedActions);

    if (decision.isRespond()) {
        goalVerifier.completeOrReject(run, decision);
        break;
    }

    if (decision.isAskUser()) {
        interactionService.waitForInput(run, decision);
        break;
    }

    AgentActionMetadata metadata = actionRegistry.getRequiredMetadata(decision.getAction());
    Map<String, Object> arguments = argumentValidator.validateAndNormalize(metadata, decision.getArguments());
    policyService.validateBeforeExecution(context, metadata, arguments);
    dedupService.rejectRepeatedCall(run, metadata, arguments);

    if (metadata.isWrite()) {
        planService.prepareWriteConfirmation(run, metadata, arguments);
        break;
    }

    AgentActionResult result = actionExecutionService.execute(context, metadata, arguments);
    observationService.appendSuccess(run, metadata, arguments, result);
}
```

### 10.2 写操作冲突处理

```java
try {
    AgentActionResult result = executeWriteAction(...);
    observationService.appendActionSucceeded(...);
    goalVerifier.verifyBusinessResult(...);
} catch (ServiceException ex) {
    AgentObservation observation = errorMapper.toObservation(ex, ...);
    observationService.append(run, observation);

    if (observation.getError().isReplanRequired()) {
        run.setStatus(RUNNING);
        executePlanningLoop(run);
        return;
    }
    fail(run, observation);
}
```

`enrichRecoveryWithCandidates()` 应删除。候选查询必须由统一循环执行。

### 10.3 Step 记录

每一次 Planner 和 Action 都必须有独立 Step：

```text
Step 1 PLAN：选择 meeting.create
Step 2 CONFIRM：等待创建确认
Step 3 ACTION：meeting.create → BUSINESS_CONFLICT
Step 4 PLAN：选择 meeting.availability.search
Step 5 ACTION：返回真实候选
Step 6 PLAN：选择 meeting.candidate.rank
Step 7 ACTION：返回排序候选
Step 8 PLAN：形成候选 Plan
```

Step 和 Observation 分工：

- Step 记录执行过程和耗时。
- Observation 记录 Planner 下一步决策所需的可信事实。

---

## 11. Goal Verifier

### 11.1 问题

LLM 返回文本不代表用户目标完成。会议安排必须以 OA Service 的真实写入结果为准。

### 11.2 规则

新增 `AgentGoalVerifier`：

```java
public interface AgentGoalVerifier {
    GoalVerificationResult verify(AgentRunDO run,
                                  AgentActionMetadata action,
                                  Map<String, Object> result);
}
```

会议创建完成条件：

- `meeting.create` 返回有效 `bookingId`。
- 数据属于当前租户。
- 申请人为当前用户。
- 状态为有效。
- 会议室和时间与固化候选一致。

只有满足上述条件，Run 才能进入 `COMPLETED`。

最终回复由 Runtime 提供事实，再由 LLM 做语言整理；LLM 不得自行生成 bookingId 或成功状态。

---

## 12. 预算、超时与错误分类

### 12.1 推荐默认预算

| 预算 | 默认值 |
|---|---|
| Planner 调用次数 | 6 |
| 只读 Action 次数 | 6 |
| 写 Action 尝试次数 | 2，且第二次必须通过 ReplanGuard |
| Run 总时长 | 45 秒 |
| LLM 总 Token | 12000 |
| 单次 LLM 超时 | 12 秒 |
| 单次 OA 只读 Action 超时 | 5 秒 |
| 候选有效期 | 5 分钟 |
| 写确认有效期 | 30 分钟 |

最终值应通过配置项控制，不能写死在 Service 中。

### 12.2 错误分类

| 类型 | 示例 | 处理 |
|---|---|---|
| `TRANSIENT_ERROR` | 网络超时、短暂 503 | 最多有限重试并指数退避 |
| `BUSINESS_CONFLICT` | 会议室 409 | 写 Observation 并 Replan |
| `VALIDATION_ERROR` | 时间格式错误 | 请求补充信息或失败 |
| `PERMISSION_DENIED` | 无会议查询权限 | 立即失败，不继续规划 |
| `BUDGET_EXHAUSTED` | 超步数或 Token | 明确说明未完成原因 |
| `FATAL_ERROR` | 数据损坏、未知状态 | 失败并告警 |

### 12.3 退避策略

仅对幂等的只读 Action 和 LLM 网络请求重试：

```text
第 1 次失败：等待 200ms
第 2 次失败：等待 500ms
之后停止并产生 TRANSIENT_ERROR Observation
```

写 Action 不做网络层盲重试。写操作超时时必须先通过幂等键查询结果，不能直接再次创建。

---

## 13. 幂等、并发与过期控制

### 13.1 规范化 Tool Key

当前 `action + JSON 字符串` 会受到 Map Key 顺序影响。改为：

```text
SHA-256(actionId + canonicalJson(normalizedArguments))
```

canonical JSON 必须：

- Map Key 排序。
- 时间格式统一。
- 数字类型统一。
- 空数组、空字符串和 null 按 Schema 规则处理。

### 13.2 写操作幂等键

```text
runId + planId + planVersion + candidateId + actionId
```

OA Service 或 Runtime 写执行记录必须对该键建立唯一约束。

### 13.3 确认过期

`selectPendingByRunId()` 和 `markExecuting()` 都必须增加：

```sql
expires_time > NOW()
```

过期确认应更新为 `EXPIRED`，Run 转为 `WAITING_PLAN_CONFIRMATION` 或 `FAILED`，不得继续执行旧快照。

### 13.4 乐观锁

所有 Run 状态更新使用 `id + version` 条件：

```sql
UPDATE agent_run
SET status = ?, version = version + 1
WHERE id = ? AND version = ?
```

并发选择候选、重复确认或取消时，只允许一个请求成功。

---

## 14. Runtime UI Schema

### 14.1 候选 Plan 卡片

```json
{
  "type": "PLAN_CONFIRMATION",
  "title": "检测到会议室冲突，已找到可行方案",
  "description": "以下方案均已通过 OA 会议室可用性校验",
  "planId": "plan-2",
  "planVersion": 2,
  "candidates": [
    {
      "candidateId": "candidate-A",
      "title": "方案 A",
      "fields": [
        {"label": "会议室", "value": "2 号会议室"},
        {"label": "时间", "value": "2026-07-16 14:00-16:00"},
        {"label": "容量", "value": "12 人"}
      ],
      "reasons": ["原时间不变", "容量满足且余量最小"]
    }
  ],
  "actions": [
    {"actionId": "plan.select", "label": "采用方案 A", "style": "PRIMARY"},
    {"actionId": "plan.more", "label": "查看更多", "style": "DEFAULT"},
    {"actionId": "cancel", "label": "取消", "style": "DEFAULT"}
  ]
}
```

### 14.2 写操作确认卡

用户选择候选后展示独立写确认：

```text
即将创建会议：
项目评审
2 号会议室
2026-07-16 14:00-16:00

[确认创建] [返回候选方案] [取消]
```

确认卡展示的数据必须来自固化的 Plan Snapshot，不能重新读取前端 inputs。

### 14.3 通用性要求

前端组件只识别：

- `type`
- `title`
- `description`
- `fields`
- `candidates`
- `inputs`
- `actions`

不得在 React 组件中判断 `meeting.create`、`MEETING_ROOM_CONFLICT` 等领域字符串。

---

## 15. 数据库改造建议

### 15.1 第一阶段最小改造

继续复用：

- `agent_run`
- `agent_step`
- `agent_confirmation`
- `agent_event`

在 `agent_run.context_json` 中增加：

```json
{
  "constraints": {},
  "observations": [],
  "currentPlan": {},
  "executedToolKeys": [],
  "budgetUsage": {}
}
```

### 15.2 生产化表结构

建议后续增加：

```text
agent_observation
agent_plan
agent_plan_candidate
agent_action_execution
```

`agent_action_execution` 至少包含：

- `idempotency_key`
- `run_id`
- `plan_id`
- `action_id`
- `request_snapshot_json`
- `result_snapshot_json`
- `status`
- `started_time`
- `finished_time`

`idempotency_key` 建立唯一索引。

---

## 16. 分阶段开发计划

### 阶段 0：安全止血

目标：封堵现有高风险问题，不改变用户流程。

开发项：

1. `MeetingCreateActionHandler` 强制 `forceConflict=false`。
2. 恢复输入改为字段白名单，不再通用 merge。
3. 增加服务端 Action Schema 校验。
4. 确认查询和执行增加过期校验。
5. `meeting.conflict.detail` 默认移除主题和申请人信息。
6. 为上述场景增加单元测试。

验收：

- 任意恢复请求携带 `forceConflict=true` 均不能进入 Handler。
- 未声明字段被拒绝并生成审计记录。
- 过期确认不能执行。

### 阶段 1：冲突 Observation 化

目标：409 进入统一事实协议。

开发项：

1. 新增 `AgentObservation` 和 `AgentObservationError`。
2. 新增 `AgentObservationService`。
3. 将只读成功结果迁移到统一 Observation。
4. 将 `MEETING_ROOM_CONFLICT` 转换为 `ACTION_FAILED` Observation。
5. 禁止进入冲突状态时覆盖原 Run Context。
6. Step 中记录冲突 Action 的失败结果。

验收：

- Run 中同时保留原始目标、历史只读结果和冲突 Observation。
- Observation 可以完整重放 Planner 输入。

### 阶段 2：真正的 Replan 循环

目标：冲突后重新进入 Planner。

开发项：

1. 删除冲突后的固定 `enrichRecoveryWithCandidates()` 调用。
2. 冲突 Observation 写入后将 Run 恢复为 `RUNNING`。
3. 重新调用 `executePlanningLoop()`。
4. 新增动态 Action Catalog。
5. 新增 ReplanGuard。
6. 相同创建参数再次出现时拒绝执行。

验收：

- Step 日志能够看到“创建冲突 → 再规划 → 查询可用会议室”。
- Planner 无法在未改变约束时再次创建。
- Planner 不能选择当前状态不允许的 Action。

### 阶段 3：Plan 与候选确认

目标：候选从错误按钮升级为可版本化 Plan。

开发项：

1. 新增 `AgentPlan` 和 `AgentPlanCandidate`。
2. 候选使用 `candidateId`，不再使用数组下标。
3. 增加 `planId`、`planVersion`、`expiresAt`。
4. 新增 `WAITING_PLAN_CONFIRMATION`。
5. 更新 Runtime UI Schema 和 React 通用卡片。
6. 候选选择后生成不可变写确认快照。

验收：

- 过期 Plan 无法选择。
- 旧版本 Plan 无法覆盖新版本。
- 前端篡改会议室和时间不会影响执行参数。

### 阶段 4：权限、预算和生产化

目标：具备生产运行边界。

开发项：

1. Action Metadata 增加权限和数据范围。
2. 接入统一权限校验。
3. 增加 Run 总时长和 Token 预算。
4. 增加有限退避和错误分类。
5. 增加规范化去重键和写操作幂等键。
6. Run 更新增加乐观锁。
7. 增加监控指标和告警。

### 阶段 5：FreeBusy 与自动调时间

该阶段不属于第一期。

开发项：

1. 新增 `calendar.freebusy.query`。
2. 增加参会人忙闲查询授权。
3. 计算共同空闲区间。
4. 区分硬约束与软偏好。
5. 支持“同会议室换时间”和“换会议室并换时间”。
6. 自动调时间仍必须让用户确认 Plan。

---

## 17. 代码改造清单

### 17.1 Runtime

重点修改：

- `DefaultAgentRuntimeService`
- `AgentRuntimeService`
- `AgentRunStatus`
- `AgentTurnResult`
- `AgentRuntimeUi`
- `AgentActionExecutionService`

新增建议：

- `AgentObservationService`
- `AgentActionPolicyService`
- `AgentActionArgumentValidator`
- `AgentReplanGuard`
- `AgentPlanService`
- `AgentBudgetService`
- `AgentGoalVerifier`
- `AgentErrorObservationMapper`

### 17.2 Planner

重点修改：

- `RuntimeToolCallingAgentPlanner`
- `AgentPlannerContext`
- `OpenAiCompatibleAgentToolCallingClient`

要求：

- Planner 接受动态允许 Action 列表。
- Observation 使用受控结构传递。
- 不把完整数据库对象直接序列化给模型。
- 记录模型用量、耗时和结束原因。

### 17.3 Action

重点修改：

- `MeetingCreateActionHandler`
- `MeetingAvailabilitySearchActionHandler`
- `MeetingCandidateRankActionHandler`
- `MeetingConflictDetailActionHandler`
- `AgentActionRegistry`
- `AgentActionMetadata`

要求：

- Availability 支持最小容量、设备和候选会议室范围。
- 自动冲突恢复必须传入参会人数对应的容量约束。
- Candidate Rank 返回评分原因。
- Conflict Detail 执行权限与字段脱敏。

### 17.4 前端和 Dify

重点修改：

- `runtime-action-card.tsx`
- Runtime UI 类型声明
- Dify Human Input 恢复参数映射

Dify 主图只增加通用状态支持：

- `WAITING_PLAN_CONFIRMATION`
- `WAITING_CONFIRMATION`
- `WAITING_INPUT`
- `COMPLETED`
- `FAILED`

禁止增加会议专用 Chatflow 分支。

---

## 18. 测试方案

### 18.1 单元测试

#### 参数和安全

- 未声明字段被拒绝。
- `forceConflict=true` 被拒绝或强制覆盖为 false。
- 恢复输入只能修改声明字段。
- 相同语义、不同 Map 顺序生成相同去重键。
- 过期确认无法执行。

#### Observation

- 只读成功写入 `TOOL_RESULT`。
- 会议冲突写入 `ACTION_FAILED/BUSINESS_CONFLICT`。
- 新 Observation 不覆盖旧 Observation。
- Observation 大字段被截断或摘要化。

#### Replan

- 冲突后重新调用 Planner。
- Planner 只能看到 `nextAllowedActions`。
- 原参数重复创建被 ReplanGuard 拒绝。
- 更换会议室且时间不变通过 ReplanGuard。
- 任意修改时间在第一期被拒绝。

#### Plan

- 候选使用稳定 `candidateId`。
- Plan 版本不匹配时拒绝选择。
- Plan 过期时拒绝选择。
- 前端提交伪造会议室参数不影响固化候选。

### 18.2 集成测试

使用 H2 或测试 MySQL 构造：

1. 1 号会议室已有冲突会议。
2. 2 号会议室同时间可用且容量满足。
3. 3 号会议室可用但容量不足。
4. 用户发起 10 人会议。

预期：

- 创建 1 号会议室返回冲突 Observation。
- Replan 查询会议室时携带 `minimumCapacity=10`。
- 2 号会议室进入候选，3 号会议室不进入。
- 用户选择 2 号会议室后进入写确认。
- 确认后只创建一条会议记录。

### 18.3 并发测试

- 两个请求同时确认，只允许一个执行。
- 用户选择候选时会议室被其他人占用，应产生新的冲突 Observation 并再次 Replan。
- 用户同时执行取消和确认，最终状态唯一且可解释。

### 18.4 端到端测试

真实 OA、Dify 和浏览器验证：

```text
用户发送创建会议请求
→ 首次确认卡
→ 制造会议室冲突
→ 页面显示自动规划过程
→ 展示真实候选 Plan
→ 选择候选
→ 二次确认
→ 创建成功
→ 数据库核对 bookingId、申请人、会议室和时间
```

同时验证：

- 浏览器篡改恢复参数不能注入业务字段。
- 无权限用户无法查询冲突详情。
- Dify 中没有新增会议专用分支。
- 刷新页面后待确认 Plan 可以恢复。

---

## 19. 监控与审计

### 19.1 指标

建议记录：

- `agent_run_total{status}`
- `agent_replan_total{reason}`
- `agent_action_duration_ms{action}`
- `agent_action_error_total{action,code}`
- `agent_planner_tokens_total{model}`
- `agent_budget_exhausted_total{type}`
- `agent_confirmation_expired_total`
- `agent_policy_rejected_total{reason}`

### 19.2 审计事件

必须审计：

- 原始写操作快照。
- 用户确认人和确认时间。
- 冲突 Observation。
- Replan 前后变化字段。
- 候选生成依据。
- 用户选择的 `planId`、版本和 `candidateId`。
- OA 最终结果。
- 被拒绝的控制字段或非法恢复参数。

日志不得记录身份票据、API Key、完整 Prompt 或其他用户的敏感日程内容。

---

## 20. 验收标准

第一期只有同时满足以下条件才能认定为“真正的受约束 Agent Replan”：

1. 会议创建 409 被写入通用 Observation。
2. 冲突后重新进入统一 Planner 循环。
3. Planner 只能看到 Runtime 动态允许的 Action。
4. Runtime 不再固定调用会议候选查询方法。
5. ReplanGuard 可以证明新方案改变了会议室约束。
6. 原创建参数不得重复执行。
7. 候选来自 OA Service 的真实查询结果。
8. 候选具有 `planId`、版本、`candidateId` 和有效期。
9. 前端不能提交或篡改候选中的业务参数。
10. 写操作仍需独立确认。
11. OA Service 进行最终冲突校验。
12. `forceConflict` 等控制字段无法从 Agent 链路进入 Service。
13. Action 权限在 Runtime 执行前校验。
14. 确认过期后不能执行。
15. 单元、集成、并发和真实环境回归全部通过。
16. 所有实现进入 Git 分支、Commit、PR 和发布记录。

---

## 21. 推荐实施顺序与工作量

| 阶段 | 内容 | 预计工作量 |
|---|---|---|
| 阶段 0 | 参数安全、`forceConflict`、确认过期、脱敏 | 1 至 2 人日 |
| 阶段 1 | Observation 统一协议 | 2 至 3 人日 |
| 阶段 2 | 动态工具集、统一 Replan、ReplanGuard | 3 至 5 人日 |
| 阶段 3 | Plan/Candidate、UI Schema、候选版本 | 3 至 5 人日 |
| 阶段 4 | 权限、预算、幂等、并发、监控 | 4 至 7 人日 |
| 测试与真实验收 | 单元、集成、Dify、数据库取证 | 3 至 5 人日 |

第一期总工作量预计为 16 至 27 人日。若暂不拆分 Observation、Plan 和执行记录数据表，可缩短约 3 至 5 人日，但必须保留后续迁移接口，避免继续扩大 `context_json` 的职责。

---

## 22. 最终交付物

- Agent Replan Runtime 代码。
- Action Policy 与参数校验代码。
- Observation、Plan、Candidate 协议类。
- 数据库升级脚本。
- Runtime OpenAPI 更新。
- Dify 通用状态图更新脚本。
- Runtime Action Card 更新。
- 单元测试、集成测试和并发测试。
- 真实环境联调验收记录。
- 安全测试记录。
- Git Commit、PR 和发布回滚说明。

完成后，项目运行逻辑应从“冲突后固定找会议室”升级为“冲突成为可信事实，Planner 在 Runtime 约束下重新制定可验证方案”。
