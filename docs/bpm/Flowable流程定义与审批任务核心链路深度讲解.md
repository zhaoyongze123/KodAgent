# Flowable 流程定义与审批任务核心链路深度讲解

这份文档讲 BPM 模块最核心的部分：流程定义、流程实例、审批任务、任务动作、事件回写。

## 一、先看结论

BPM 模块不是只存流程图，而是完整管理三类对象：

1. **流程定义**：流程模型、表单、监听器、表达式、候选人策略。
2. **流程实例**：某个业务单据到底跑到了哪一步。
3. **审批任务**：当前谁待办、谁审批、谁转办、谁退回。

真正业务落地时，流程和业务表通过 `businessKey` 绑定。

## 二、流程定义链路

### 1. 核心服务

定义侧的核心服务包括：

- `BpmModelServiceImpl`
- `BpmProcessDefinitionServiceImpl`
- `BpmFormServiceImpl`
- `BpmProcessExpressionServiceImpl`
- `BpmProcessListenerServiceImpl`
- `BpmUserGroupServiceImpl`

### 2. 这层在做什么

它负责把一个流程从“编辑态”变成“可运行态”。

典型职责：

- 维护 BPMN 模型
- 维护流程定义
- 维护表单
- 维护监听器
- 维护候选人规则

### 3. 为什么要有 `ProcessDefinitionInfo`

Flowable 原生的 `ProcessDefinition` 不够表达业务扩展信息，所以仓库自己又补了一层 `BpmProcessDefinitionInfoDO`。

这体现的是一个很重要的架构思路：

**引擎对象只负责运行，业务扩展对象负责承载平台语义。**

## 三、流程实例链路

### 1. 核心服务

流程实例侧的核心服务包括：

- `BpmProcessInstanceServiceImpl`
- `BpmProcessInstanceApiImpl`
- `BpmProcessInstanceStatusEvent`
- `BpmProcessInstanceStatusEventListener`
- `BpmProcessInstanceEventPublisher`

### 2. 发起流程的基本逻辑

业务单据保存后，会调用流程实例 API 创建实例。

创建流程实例时会带上：

- 业务 key
- 发起人
- 表单变量
- 流程定义 key
- 租户信息

### 3. 为什么要发事件

审批结束后，系统会发流程状态事件，再由业务监听器回写业务表。

这是为了让 BPM 和业务域解耦。

## 四、审批任务链路

### 1. 核心服务

任务侧的核心服务包括：

- `BpmTaskServiceImpl`
- `BpmProcessInstanceCopyServiceImpl`
- 各种 task listener / trigger / candidate strategy

### 2. 任务操作有哪些

`BpmTaskService` 里能看到一整套动作：

- 审批
- 拒绝
- 转办
- 退回
- 委派

这说明 BPM 不是只有“同意/不同意”两个按钮，而是完整的任务生命周期管理。

### 3. 候选人策略怎么接入

BPM 通过 `BpmTaskCandidateStrategyEnum` 和一组策略实现，决定某个节点的候选审批人是谁。

这就是典型的策略模式。

## 五、Flowable 配置层做了什么

`BpmFlowableConfiguration` 是非常关键的集成点。

它会：

- 创建 Flowable 需要的线程池
- 注入事件监听器
- 注入自定义函数
- 注入活动行为工厂
- 注入任务候选人解析器
- 发布流程事件

也就是说，Flowable 本身只是引擎，真正让它“懂业务”的是这一层配置和扩展。

## 六、OA 请假样板为什么重要

`BpmOALeaveServiceImpl` + `BpmOALeaveStatusListener` 是整个 BPM 最适合拿来教学的样板。

它告诉你：

- 业务表怎么建
- 流程实例怎么发起
- 状态怎么同步
- 审批结束怎么回写
- 业务和流程怎么解耦

## 七、你要掌握的 Java / 架构知识

### 1. 工作流引擎集成

引擎不是业务，集成层才是业务。

### 2. 事件驱动

审批状态回写最好通过事件。

### 3. 策略模式

候选人规则天然适合策略化。

### 4. 状态机思维

流程实例和任务就是状态流转。

## 八、你以后读 BPM 的顺序

建议顺序：

1. `BpmFlowableConfiguration`
2. `BpmProcessDefinitionServiceImpl`
3. `BpmProcessInstanceServiceImpl`
4. `BpmTaskServiceImpl`
5. `BpmOALeaveServiceImpl`
6. `BpmOALeaveStatusListener`

把这条链路看懂，你就知道 BPM 不是“流程图工具”，而是“业务单据 + 引擎 + 事件回写”的完整系统。
