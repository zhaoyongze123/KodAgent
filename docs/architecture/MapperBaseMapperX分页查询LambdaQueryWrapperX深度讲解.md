# Mapper / BaseMapperX / 分页查询 / LambdaQueryWrapperX 深度讲解

这份文档讲的是这套仓库里最常见、最基础、也最容易被写烂的一层：数据库访问。

## 一、先看结论

这套仓库没有把 MyBatis Plus 直接裸着用，而是在它上面再包了一层自己的约定：

- `Mapper` 负责表级访问。
- `BaseMapperX` 负责统一分页、批量、单查、连表等常用能力。
- `LambdaQueryWrapperX` / `MPJLambdaWrapperX` 负责更顺手的条件拼接。
- `PageResult` 负责统一分页返回。

这套设计的目的不是“多包一层”，而是减少每个模块重复写 CRUD 样板。

## 二、Mapper 是什么

`Mapper` 是表级访问入口。

在这套仓库里，很多 Mapper 都继承 `BaseMapperX<T>`，比如：

- `BpmOALeaveMapper`
- `FileMapper`
- `ConfigMapper`
- `BpmProcessExpressionMapper`

Mapper 的职责很明确：

- 只做数据库查询/写入
- 不做业务编排
- 不写 Controller 逻辑

## 三、BaseMapperX 为什么存在

对应代码：

`yudao-framework/yudao-spring-boot-starter-mybatis/src/main/java/cn/iocoder/yudao/framework/mybatis/core/mapper/BaseMapperX.java`

它是在 MyBatis Plus `BaseMapper` 上扩展出来的。

### 1. 它补了什么

它补了很多仓库里高频使用的能力：

- `selectPage(...)`
- `selectJoinPage(...)`
- `selectOne(...)`
- `selectFirstOne(...)`
- `selectCount(...)`
- `selectList(...)`
- `insertBatch(...)`
- `updateBatch(...)`
- `deleteBatch(...)`

### 2. 为什么不直接用 MyBatis Plus 原生接口

因为原生 `BaseMapper` 太底层，重复代码太多。

这套仓库高频业务大量都是：

- 条件查询
- 分页查询
- 批量插入
- 批量更新
- 批量删除

如果每个 Mapper 都手写一遍，代码会非常碎。

### 3. `selectPage(...)` 的关键逻辑

`BaseMapperX.selectPage(...)` 里有一个非常重要的设计：

- 如果 `pageSize == PAGE_SIZE_NONE`，直接查全量，不分页。
- 否则构建 MyBatis Plus 分页对象，再执行分页查询。

这让“查全部”和“分页查”复用同一个入口。

## 四、分页查询为什么统一用 PageResult

`PageResult<T>` 是项目统一的分页结构。

它解决的问题是：

- 前后端分页格式统一
- 各模块分页接口返回一致
- 业务代码不需要直接暴露 MyBatis 的 `IPage`

所以你在仓库里常见这种写法：

- Mapper 返回 `PageResult<DO>`
- Controller 再把 `DO` 转成 `VO`

## 五、LambdaQueryWrapperX 是什么

对应代码：

`yudao-framework/yudao-spring-boot-starter-mybatis/src/main/java/cn/iocoder/yudao/framework/mybatis/core/query/LambdaQueryWrapperX.java`

它是对 MyBatis Plus `LambdaQueryWrapper` 的扩展。

### 1. 它增加了什么

最核心的是一批 `xxxIfPresent` 方法：

- `likeIfPresent`
- `inIfPresent`
- `eqIfPresent`
- `neIfPresent`
- `gtIfPresent`
- `geIfPresent`
- `ltIfPresent`
- `leIfPresent`
- `betweenIfPresent`

### 2. 为什么要有这些方法

因为很多查询参数是可选的。

比如：

- 名称可选
- 状态可选
- 时间范围可选
- 分类可选

如果不用这些方法，你就得写大量 `if (param != null)` 再拼条件。

### 3. 这类方法的意义

它把“是否拼 SQL 条件”的逻辑封装到了 wrapper 层，而不是让每个 Mapper 自己写一堆 if。

## 六、MPJLambdaWrapperX 是什么

它是连表查询 wrapper 的扩展版。

作用和 `LambdaQueryWrapperX` 类似，但面向多表 join 场景。

这对复杂列表页非常有用。

## 七、真实代码怎么用

### 1. BPM 请假表

`BpmOALeaveMapper` 里会用：

- `selectPage(reqVO, new LambdaQueryWrapperX<...>()... )`

这是非常典型的写法。

### 2. 文件模块

`FileMapper`、`FileConfigMapper`、`ConfigMapper` 也是同样模式。

### 3. BPM 审批任务

`BpmProcessInstanceCopyMapper`、`BpmProcessExpressionMapper` 等也在用这套查询封装。

## 八、你要掌握的 Java / 架构知识

### 1. 泛型

`BaseMapperX<T>`、`PageResult<T>`、`LambdaQueryWrapperX<T>` 都依赖泛型设计。

### 2. 模板复用

通过基类减少重复代码。

### 3. 条件构造

查询条件要按“有值才拼”来写。

### 4. 连表抽象

复杂查询需要更高层 wrapper，不应该直接把 SQL 散落到业务里。

## 九、你以后看 Mapper 的顺序

建议固定顺序：

1. 先看 Mapper 继承了什么。
2. 再看它用的是 `selectPage` 还是自定义 SQL。
3. 再看它是不是用了 `LambdaQueryWrapperX`。
4. 最后看 Service 为什么要调用这个 Mapper。

把这套规则看懂，你就知道为什么企业项目里 Mapper 看上去简单，实际上是整个 CRUD 体系的骨架。
