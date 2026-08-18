# 前后端接口契约与 VO/DTO/DO/Convert 分层深度讲解

这份文档讲清楚这套仓库里最重要、也最容易被新人写乱的东西：接口契约和对象分层。

## 一、先看结论

这套仓库不是“一个对象到处传”，而是明确分了几层：

- `VO`：给前端的接口对象。
- `DTO`：模块内、模块间传递对象。
- `DO`：数据库对象。
- `Convert`：负责对象转换。

它们各自有边界，不能混用。

## 二、为什么一定要分层

如果把所有字段都塞进一个类，短期看很快，长期一定会出问题：

- 前端字段和数据库字段会绑死。
- 新增查询字段会污染写入模型。
- 接口返回结构会被表结构拖着走。
- 一个表一改，前端接口跟着炸。

所以分层的本质不是“好看”，而是**隔离变化**。

## 三、DO 是什么

`DO` 是数据库对象，直接映射表。

典型例子：

- `BpmOALeaveDO`
- `FileDO`
- `OperateLogDO`
- `ApiAccessLogDO`

DO 的原则：

- 尽量贴近表结构
- 主要表达持久化字段
- 不承载前端展示语义

## 四、VO 是什么

`VO` 是接口对象，专门给前端用。

典型例子：

- `AuthLoginReqVO`
- `FileUploadReqVO`
- `RoleRespVO`
- `MenuSaveVO`

VO 的原则：

- 适配前端输入输出
- 可以做校验注解
- 可以带展示字段
- 不要直接暴露数据库内部结构

## 五、DTO 是什么

`DTO` 主要用于模块内部、模块间传递。

典型例子：

- `SmsCodeSendReqDTO`
- `SmsCodeUseReqDTO`
- `OperateLogCreateReqDTO`
- `BpmProcessInstanceCreateReqDTO`

DTO 的原则：

- 适合服务间调用
- 适合 API 层转业务层
- 不一定适合直接返回前端

## 六、Convert 是什么

`Convert` 是对象转换层。

它在这套项目里大量使用 MapStruct 或工具类转换。

典型例子：

- `AuthConvert`
- `ConfigConvert`
- `FileConfigConvert`
- `BpmProcessDefinitionConvert`

### 1. Convert 的职责

- DTO -> DO
- DO -> VO
- 多个对象拼装成一个返回对象
- 局部补充业务字段

### 2. 为什么不用手写一堆 `new`

因为对象转换是重复劳动，而且很容易漏字段。

转换层单独抽出来之后：

- 可维护性更好
- 字段变更更容易检查
- 业务代码更清晰

## 七、真实代码里的例子

### 1. 登录接口

`AuthLoginReqVO` 是前端提交的登录请求。

它里面有：

- `username`
- `password`
- `socialType`
- `socialCode`
- `socialState`

它还带了验证注解，说明 VO 不只是“数据容器”，还是“接口契约”。

`AuthConvert` 会把它转成：

- `SmsCodeSendReqDTO`
- `SmsCodeUseReqDTO`
- `SocialUserBindReqDTO`

这就是典型的“VO 进来，DTO 转发给业务服务”。

### 2. 文件上传接口

`FileUploadReqVO` 里放的是：

- `MultipartFile file`
- `directory`

它还自己校验目录是否合法，防止目录穿越。

这说明 VO 里可以包含接口级验证逻辑，但不要把业务逻辑塞进来。

### 3. 操作日志接口

`OperateLogCreateReqDTO` 会被 `OperateLogServiceImpl` 转成 `OperateLogDO` 落库。

也就是说：

- 传输对象负责承接请求
- DO 负责持久化

### 4. BPM 流程定义接口

`BpmProcessDefinitionConvert` 会把 Flowable 原生对象和业务扩展对象拼成前端需要的 `RespVO`。

这说明 Convert 不只是“简单复制字段”，有时还要做聚合和补全。

## 八、前后端接口契约是什么

接口契约不是口头约定，而是这几类东西共同构成的：

- 请求 VO 字段
- 返回 VO 字段
- 校验注解
- 枚举值
- 分页结构
- 统一响应 `CommonResult`

前端和后端真正对齐的，不只是 URL，而是这些结构化契约。

## 九、你要掌握的 Java / 架构知识

### 1. 单一职责

一个对象只干一类事。

### 2. 数据封装

不同层对象承载不同语义。

### 3. 映射与适配

Convert 是典型适配层。

### 4. 校验注解

VO 最常配合 JSR-303 校验。

### 5. 面向变化隔离

表结构变动不应直接冲击接口结构。

## 十、你以后读这类代码的顺序

建议按这个顺序：

1. 先看 Controller 的入参 VO 和出参 VO。
2. 再看 Service 的 DTO。
3. 再看 DO 和 Mapper。
4. 最后看 Convert 怎么拼装和转换。

把这条线看顺，你就会知道为什么企业项目里最怕“一个对象传到底”。
