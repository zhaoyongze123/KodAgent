# 操作日志与 API 日志链路深度讲解

这份文档讲清楚两类日志是怎么进系统的：操作日志和 API 访问日志。

## 一、先看结论

这套仓库的日志不是简单打印到控制台，而是分成两条线：

1. **操作日志**：记录“谁做了什么业务操作”。
2. **API 访问日志**：记录“哪个接口被谁调用、耗时多久、结果怎样”。

它们不是同一件事。

- 操作日志偏业务行为。
- API 日志偏接口请求。

## 二、操作日志链路

### 1. 入口在哪里

你在很多 Controller 上能看到 `@ApiAccessLog`，例如导出、列表等接口。

但真正的操作日志落库，不在 Controller 里硬写，而是通过统一的日志服务接口实现。

### 2. 核心类

从源码看，相关核心类包括：

- `OperateLogDO`
- `OperateLogServiceImpl`
- `OperateLogApi`
- `OperateLogApiImpl`

### 3. 数据流怎么走

一个典型操作日志链路是：

1. Controller 触发某个业务操作。
2. AOP 或统一日志机制收集请求信息、操作类型、模块、结果。
3. 构建 `OperateLogCreateReqDTO`。
4. 调 `OperateLogServiceImpl.createOperateLog(...)`。
5. 转成 `OperateLogDO` 落库。

### 4. 为什么要独立成日志模块

因为日志是横切能力，不应该散落在每个业务方法里。

如果每个业务都自己写日志：

- 格式不统一
- 字段不统一
- 查询不统一
- 清理不统一

## 三、API 访问日志链路

### 1. 入口在哪里

API 访问日志主要围绕 `@ApiAccessLog` 注解展开。

在 `infra` 模块里可以看到：

- `ApiAccessLogDO`
- `ApiAccessLogApiImpl`
- `ApiAccessLogService`
- `AccessLogCleanJob`

### 2. 记录什么

通常会记录：

- 请求地址
- 请求参数
- 响应结果
- 耗时
- 用户信息
- 链路追踪号
- 成功/失败状态

### 3. 为什么和错误日志是两条线

API 访问日志是“这次请求发生了什么”；
错误日志是“这次请求为什么失败”。

两者可以通过 traceId 关联起来，但职责不同。

### 4. 为什么要有清理任务

日志会无限增长，所以有 `AccessLogCleanJob` 定期清理。

这是企业系统非常典型的“运行期治理”能力。

## 四、你要掌握的 Java / 架构知识

### 1. AOP

日志最常见的实现方式就是切面。

### 2. 注解驱动

`@ApiAccessLog` 是声明式日志开关。

### 3. 数据归档与清理

日志不能永远堆在主库里。

### 4. 链路追踪

traceId 是把请求、日志、异常串起来的关键。

## 五、你以后读日志链路的顺序

建议这样读：

1. `@ApiAccessLog` 的使用位置
2. `OperateLogServiceImpl`
3. `ApiAccessLogApiImpl`
4. `ApiAccessLogDO` / `OperateLogDO`
5. `AccessLogCleanJob`

把这条链路看懂，你就知道“日志不是打印文本，而是系统治理能力”。
