# BPM 中的 Java 八股知识与代码架构

本文结合 `yudao-module-bpm` 现有代码，说明做一个 BPM 功能时会用到哪些 Java / Spring / MyBatis / Flowable 基础知识。

## 一、先理解这个模块在做什么

`yudao-module-bpm` 是工作流模块，核心职责不是存业务数据，而是管理流程定义、流程实例、待办任务、审批结果和消息通知。它本身依赖 `system`、`security`、`mybatis`、`excel` 和 `flowable`，说明它既有普通 Web 应用的分层，也有工作流引擎的运行时能力。

你可以把它理解成两层：

1. 业务层：比如请假、合同审批、收入确认，这些是“谁发起什么单据”。
2. 流程层：Flowable 负责“谁审批、怎么流转、什么时候结束”。

业务层和流程层通过 `businessKey` 绑定。

## 二、这套代码里最常见的 Java 八股知识

### 1. 面向对象

代码里最典型的是 `DO`、`VO`、`DTO`、`Service`、`Controller` 分层。

- `DO`：数据库对象，直接映射表结构，例如 [BpmOALeaveDO.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/dal/dataobject/oa/BpmOALeaveDO.java:1)
- `VO`：接口对象，给前端用，例如 [BpmOALeaveCreateReqVO.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/controller/admin/oa/vo/BpmOALeaveCreateReqVO.java:1)
- `DTO`：模块内部传输对象，例如 [BpmProcessInstanceCreateReqDTO.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/api/task/dto/BpmProcessInstanceCreateReqDTO.java:1)

这个拆分本质上是在练 OOP 的“职责单一”：

- 数据模型和接口模型分开
- 业务输入和流程输入分开
- 流程状态和业务状态分开

### 2. 接口与实现分离

例如 `BpmOALeaveService` 和 `BpmOALeaveServiceImpl`。接口定义“能做什么”，实现定义“怎么做”。

这就是 Java 里的多态和依赖倒置：上层只依赖接口，不关心具体实现。

### 3. 事务

`createLeave` 上用了 `@Transactional(rollbackFor = Exception.class)`。

这表示“先写业务表，再发起流程，再回写流程实例 ID”必须作为一个原子动作处理。任何一步失败，前面写入的数据都要回滚。

这是做 BPM 功能最关键的八股之一：

- 不能先发流程再落库，否则 `businessKey` 没法稳定绑定。
- 不能只存一半数据，否则单据和流程会脱节。

### 4. Bean 注入与依赖注入

代码大量使用 `@Resource`、`@Service`、`@Component`、`@Configuration`。

Spring 通过容器管理对象，业务代码只声明依赖，不自己 `new`。

例如：

- `BpmOALeaveServiceImpl` 注入 `BpmOALeaveMapper`、`BpmProcessInstanceApi`
- `BpmOALeaveStatusListener` 注入 `BpmOALeaveService`
- `BpmFlowableConfiguration` 注入 `BpmTaskCandidateInvoker`

这就是依赖注入的典型用法。

### 5. 事件驱动

`BpmProcessInstanceStatusEvent` 继承 `ApplicationEvent`，`BpmProcessInstanceEventPublisher` 负责发布事件，`BpmOALeaveStatusListener` 负责监听事件。

这对应 Java 里的观察者模式：

- 发布者不直接调用业务类
- 业务监听器自己响应状态变化

这样做的好处是解耦。BPM 不需要知道“请假单怎么更新”，只负责发事件。

### 6. 注解驱动编程

这个模块很多逻辑都依赖注解：

- `@RestController`：声明接口类
- `@RequestMapping`：定义路由
- `@Validated`：参数校验
- `@Valid`：递归校验请求对象
- `@PreAuthorize`：权限控制
- `@Schema`：接口文档
- `@TableName`、`@TableId`：MyBatis Plus 映射

这就是 Spring 生态里非常典型的“注解配置代替 XML 配置”。

### 7. 泛型

泛型在这里很常见：

- `CommonResult<Long>`
- `PageResult<BpmOALeaveDO>`
- `Map<String, Object>`
- `List<BpmTaskCandidateStrategy>`

泛型的目的有两个：

- 提升类型安全
- 减少强转

### 8. 集合与 Map

BPM 很多页面不是单表查询，而是“拼装页”。

例如 `BpmProcessInstanceController` 会把流程实例、任务、流程定义、分类、用户、部门拼起来一起返回。

这类代码会大量用到：

- `Map`
- `List`
- `Set`
- `convertSet`
- `convertList`
- `convertSetByFlatMap`

这是 Java 集合和流式思维的实际应用。

### 9. 枚举

`BpmTaskStatusEnum`、`BpmProcessInstanceStatusEnum`、`BpmReasonEnum` 等枚举负责把“状态码”变成“有语义的常量”。

这比直接写数字强很多，因为：

- 可读性更高
- 不容易写错
- 可以集中维护字典值

### 10. 异常处理

代码里会用 `exception(...)` 抛业务异常，例如 `OA_LEAVE_NOT_EXISTS`、`PROCESS_INSTANCE_NOT_EXISTS`。

这属于 Java 里的受控错误处理：不是直接让系统崩掉，而是抛出可识别的业务错误码给前端。

## 三、这套代码里的关键框架知识

### 1. Spring MVC

Controller 负责接 HTTP 请求，再调用 Service。

例如 [BpmOALeaveController.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/controller/admin/oa/BpmOALeaveController.java:1)：

- `POST /bpm/oa/leave/create`
- `GET /bpm/oa/leave/get`
- `GET /bpm/oa/leave/page`

这就是典型的 REST 风格接口。

### 2. MyBatis Plus

`BpmOALeaveDO` 用 `@TableName` 映射表，`BpmOALeaveMapper` 继承 `BaseMapperX`。

这说明它不是手写 JDBC，而是通过 ORM 层做持久化。

### 3. Flowable

Flowable 是 BPM 的核心引擎。`BpmProcessInstanceServiceImpl` 和 `BpmTaskServiceImpl` 直接操作：

- `RuntimeService`
- `HistoryService`
- `TaskService`
- `ProcessInstance`
- `HistoricProcessInstance`

这部分属于工作流引擎 API，不是普通业务 CRUD。

### 4. 事件与配置

`BpmFlowableConfiguration` 是整个 Flowable 接入的关键配置类。

它做了三件事：

1. 提供 `applicationTaskExecutor`，避免 Flowable 启动时报线程池问题。
2. 注册自定义监听器。
3. 注册自定义 `ActivityBehaviorFactory` 和函数委托。

这说明工作流不是“纯配置即可”，而是要通过 Spring 配置接入运行时行为。

## 四、理解业务与流程为什么要分开

在 `OA 请假` 里，业务单据存的是：

- 请假时间
- 请假类型
- 原因
- 状态
- 流程实例 ID

流程实例存的是：

- 当前节点
- 当前审批人
- 历史任务
- 流程变量
- 审批记录

这两类数据不能混在一起。

原因很简单：

- 业务单据是“业务真相”
- 流程实例是“审批过程”

审批过程可能重试、撤回、取消、加签，但业务单据本身只关心最终状态和必要的流程引用。

