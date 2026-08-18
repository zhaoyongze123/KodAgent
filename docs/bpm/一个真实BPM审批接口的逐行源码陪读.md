# 一个真实 BPM 审批接口的逐行源码陪读

这份文档选一个最真实、最典型的接口来逐行看：`BpmTaskController.approveTask()`。

它对应的是：审批人点击“通过”按钮，系统完成一次任务审批。

## 一、先看入口

对应代码：

`yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/controller/admin/task/BpmTaskController.java`

接口是：

```java
@PutMapping("/approve")
public CommonResult<Boolean> approveTask(@Valid @RequestBody BpmTaskApproveReqVO reqVO) {
    taskService.approveTask(getLoginUserId(), reqVO);
    return success(true);
}
```

### 1. 这一层做了什么

它只做三件事：

- 接收请求体 `BpmTaskApproveReqVO`
- 从上下文拿当前登录人 id
- 调 `taskService.approveTask(...)`

### 2. 这一层没做什么

它没有：

- 不查数据库
- 不判断流程逻辑
- 不写 Flowable 细节
- 不拼审批动作结果

这就是 Controller 的边界。

## 二、进入 Service 层

对应代码：

`yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/task/BpmTaskServiceImpl.java`

真正的审批逻辑都在这里。

### 1. 先看它依赖了什么

它注入了：

- `TaskService`
- `HistoryService`
- `RuntimeService`
- `ManagementService`
- `BpmProcessInstanceService`
- `BpmProcessDefinitionService`
- `BpmProcessInstanceCopyService`
- `BpmModelService`
- `BpmMessageService`
- `BpmFormService`
- `AdminUserApi`
- `DeptApi`

这说明审批不是单一表操作，而是：

- Flowable 运行时操作
- 历史任务操作
- 流程实例操作
- 消息通知
- 用户/部门信息拼装

### 2. 为什么 `approveTask` 很关键

虽然这里你看到的是一层入口，但它背后会涉及：

- 校验当前任务是不是自己的
- 判断任务状态是不是可审批
- 更新 Flowable 任务状态
- 记录审批意见
- 推动流程流转到下一节点
- 触发消息和事件

## 三、审批列表接口怎么拼数据

`BpmTaskController` 里还有一个更能体现架构能力的接口：`todo-page`。

它的流程是：

1. `taskService.getTaskTodoPage(...)` 查待办任务分页。
2. `processInstanceService.getProcessInstanceMap(...)` 拼流程实例。
3. `adminUserApi.getUserMap(...)` 拼发起人信息。
4. `processDefinitionService.getProcessDefinitionInfoMap(...)` 拼流程定义扩展信息。
5. `BpmTaskConvert.INSTANCE.buildTodoTaskPage(...)` 把所有数据组装成前端需要的 VO。

这说明 BPM 的列表页不是“查一张表”，而是**多个系统对象拼装后的业务视图**。

## 四、为什么要这么复杂

因为流程任务页面需要展示的信息很多：

- 任务本身
- 流程实例
- 发起人
- 流程定义
- 当前节点
- 表单信息
- 审批状态

这些信息分散在不同地方，不可能靠单表解决。

## 五、任务服务里最值得你看的点

### 1. 待办查询

`getTaskTodoPage(...)` 使用 `TaskQuery`，按：

- 当前审批人
- 当前激活任务
- 流程变量
- 租户
- 名称、分类、定义 key、时间范围

来做条件过滤。

### 2. 已办查询

`getTaskDonePage(...)` 用 `HistoricTaskInstanceQuery` 查历史任务。

这说明 BPM 里要区分：

- runtime task：当前待办
- historic task：已经完成的任务

### 3. 验证任务归属

`validateTask(userId, taskId)` 会检查：

- 任务是否存在
- 当前用户是不是 assignee
- 特殊情况下是否允许通过加签逻辑处理

这一步是防止“别人来审批我的任务”。

### 4. 任务动作不止通过

BPM 不只是 `approveTask`，还有：

- `rejectTask`
- `returnTask`
- `delegateTask`
- `transferTask`
- `createSignTask`
- `deleteSignTask`
- `copyTask`
- `withdrawTask`

这说明一个审批任务是一个完整生命周期，不是单按钮。

## 六、逐行看审批接口时你应该抓什么

你不要只看方法名，要按这个顺序抓：

1. 这个方法接收什么 VO。
2. 它拿到了哪些上下文信息。
3. 它调用了哪个 service。
4. 这个 service 的依赖是什么。
5. 它最终是操作 Flowable 的 Task 还是 HistoricTask。
6. 它有没有触发消息、事件、回写。

## 七、这个接口背后的设计思想

### 1. Controller 轻

只做 HTTP 装配。

### 2. Service 重

真正的业务编排都在 Service。

### 3. Flowable 只是引擎

你必须通过自己的 service 包一层，才能把它变成企业业务能力。

### 4. 前端展示靠 Convert

页面要显示的东西，不应该在 Service 里直接拼字符串返回。

## 八、你以后看 BPM 审批接口的顺序

建议固定顺序：

1. `BpmTaskController.approveTask()`
2. `BpmTaskServiceImpl.approveTask()`
3. `BpmTaskServiceImpl.validateTask()`
4. `BpmTaskServiceImpl.getTaskTodoPage()`
5. `BpmTaskConvert`
6. `BpmProcessInstanceService`
7. `BpmProcessDefinitionService`

把这条链路看懂，你就不是在看一个“审批接口”，而是在看整个 BPM 任务系统如何被组织起来。
