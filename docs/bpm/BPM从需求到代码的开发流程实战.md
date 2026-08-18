# BPM 从需求到代码的开发流程实战

本文结合 `yudao-module-bpm` 现有 `OA 请假` 示例，手把手说明一个 BPM 功能从需求到代码应该怎么落地。

## 一、先看一个真实例子：OA 请假

请假功能的完整链路是：

1. 用户填写请假单。
2. 系统先写入业务表 `bpm_oa_leave`。
3. 系统调用 BPM API 创建流程实例。
4. Flowable 开始流转审批。
5. 审批结果通过事件回写到业务表。

对应代码是：

- 控制器：[BpmOALeaveController.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/controller/admin/oa/BpmOALeaveController.java:1)
- 业务实现：[BpmOALeaveServiceImpl.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/oa/BpmOALeaveServiceImpl.java:1)
- 数据对象：[BpmOALeaveDO.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/dal/dataobject/oa/BpmOALeaveDO.java:1)
- 审批结果监听器：[BpmOALeaveStatusListener.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/oa/listener/BpmOALeaveStatusListener.java:1)
- 流程实例 API：[BpmProcessInstanceApi.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/api/task/BpmProcessInstanceApi.java:1)

## 二、第一步：从需求里拆出“业务单据”

做 BPM 功能时，第一件事不是写流程，而是先问：

“我要审批的对象是什么？”

在请假例子里，对象是请假单，所以先定义业务表：

```java
private Long id;
private Long userId;
private Integer type;
private String reason;
private LocalDateTime startTime;
private LocalDateTime endTime;
private Long day;
private Integer status;
private String processInstanceId;
```

这里的核心思路是：

- `id`：业务主键
- `status`：业务最终状态
- `processInstanceId`：和 BPM 流程绑定

如果你做的是“项目合同审批”，就先定义合同审批单，而不是先去想流程图。

## 三、第二步：定义接口入参和出参

请假功能已经把接口参数拆好了：

- `BpmOALeaveCreateReqVO`：创建时用
- `BpmOALeavePageReqVO`：分页列表用
- `BpmOALeaveRespVO`：详情和列表返回用

这一步的目的，是把前端要传什么、后端要返回什么提前固定。

例如创建请假时要传：

- 开始时间
- 结束时间
- 请假类型
- 原因
- 发起人自选审批人

这就是典型的“接口契约先行”。

## 四、第三步：先做数据库持久化，再发起流程

请假 Service 的核心代码顺序非常重要：

```java
leaveMapper.insert(leave);
String processInstanceId = processInstanceApi.createProcessInstance(...);
leaveMapper.updateById(new BpmOALeaveDO().setId(leave.getId()).setProcessInstanceId(processInstanceId));
```

为什么必须这样写：

1. 先落业务表，保证业务单据存在。
2. 再创建流程实例，拿到 `processInstanceId`。
3. 最后回写流程编号，完成绑定。

如果反过来做，流程创建成功但业务单据没落库，就会出现孤儿流程。

## 五、第四步：用 `businessKey` 绑定流程和业务

这是 BPM 开发的核心概念。

请假示例里：

```java
.setBusinessKey(String.valueOf(leave.getId()))
```

`businessKey` 的作用就是告诉 BPM：

“这个流程对应哪条业务单。”

以后你看待 BPM 时，记住这个关系：

- 业务表存自己的字段
- 流程实例存审批过程
- `businessKey` 是两者的桥

## 六、第五步：定义流程 key

请假功能里定义了：

```java
public static final String PROCESS_KEY = "oa_leave";
```

这个 key 必须和流程模型里的 key 一致。

它的作用是：

- 找到正确的流程定义
- 在事件监听时识别这个流程
- 在前端创建流程时知道用哪个模型

如果你做“项目合同审批”，就会有自己的 key，比如 `project_contract_approval`。

## 七、第六步：加一个事件监听器，把审批结果回写业务表

请假功能的监听器是：

[BpmOALeaveStatusListener.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/oa/listener/BpmOALeaveStatusListener.java:1)

核心逻辑很简单：

```java
protected String getProcessDefinitionKey() {
    return BpmOALeaveServiceImpl.PROCESS_KEY;
}

protected void onEvent(BpmProcessInstanceStatusEvent event) {
    leaveService.updateLeaveStatus(Long.parseLong(event.getBusinessKey()), event.getStatus());
}
```

这说明：

- 同一个事件系统里可以有很多监听器
- 每个监听器只处理自己关心的流程
- 审批结束后，业务状态回写到自己的业务表

这一步是“BPM 真正落到业务里”的关键。

## 八、第七步：Controller 只做参数接入，不写业务逻辑

请假 Controller 很标准：

- 创建
- 查询详情
- 分页查询

它只负责：

- 接请求
- 校验参数
- 做权限控制
- 调 Service
- 返回结果

这就是分层架构里 Controller 的职责。

## 九、第八步：流程实例 API 只是内部门面

`BpmProcessInstanceApi` 的作用是给业务模块调用：

```java
String createProcessInstance(Long userId, BpmProcessInstanceCreateReqDTO reqDTO)
```

你可以把它理解成“业务模块调用 BPM 的统一入口”。

业务模块不直接碰 Flowable 的底层 API，而是通过这一层进入流程引擎。

这样做的好处是：

- 统一封装流程创建逻辑
- 后续流程引擎变化时，业务代码不用大改
- 业务模块的依赖更干净

## 十、如果你自己要做一个新功能，就按这个顺序写

以“项目合同审批”为例，真实开发顺序应该是：

1. 先定业务表：合同审批单存什么字段。
2. 再定 VO：创建、分页、详情分别传什么。
3. 写 DO 和 Mapper：把单据落库。
4. 写 Service：先存业务表，再创建流程实例。
5. 定义流程 key：例如 `project_contract_approval`。
6. 写事件监听器：审批结果回写业务表。
7. 配 Controller 和权限：创建、查询、分页。
8. 配 BPM 流程模型：让 key 和流程图对应。
9. 最后补前端页面：列表、创建、详情、审批流转单。

## 十一、最重要的开发原则

不要把“审批”理解成一个孤立模块。

正确理解是：

- 业务模块负责“单据”
- BPM 负责“流程”
- 事件负责“状态回写”

只要这三件事分清楚，任何新的 BPM 功能都能照着这个模板写出来。

