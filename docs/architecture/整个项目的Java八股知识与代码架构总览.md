# 整个项目的 Java 八股知识与代码架构总览

本文的目标，不是给你一份“目录说明书”，而是给你一套能够真正读懂这套代码仓库的认知框架。

读完之后，你应该能回答这些问题：

1. 这个仓库到底是单体、模块化单体，还是伪微服务。
2. 请求从浏览器打进来之后，经过了哪些过滤器、拦截器、权限校验、租户校验、数据权限，再到 Controller、Service、Mapper、数据库。
3. `system`、`infra`、`bpm` 三个业务模块分别负责什么，为什么这么切。
4. `yudao-framework` 这一层为什么要拆成一堆 starter，而不是把所有公共代码塞到一个 util 包里。
5. 为什么这里选择 `Spring Boot + MyBatis Plus + OAuth2 Token + Redis + Flowable`，而不是 `Spring Security Session + JPA + Activiti` 之类的组合。
6. 当你要新增一个功能时，应该往哪里放代码，怎么设计边界，怎么避免把系统写坏。

这份文档只基于当前工作区里的**真实启用代码**来讲，不把 README 里理论上可扩展的所有模块都混成当前运行态。

## 一、先认清当前仓库的真实运行边界

### 1. 根工程当前启用的 Maven 模块

根工程 [pom.xml](../../pom.xml:1) 当前真实启用的是：

- `yudao-dependencies`
- `yudao-framework`
- `yudao-server`
- `yudao-module-system`
- `yudao-module-infra`
- `yudao-module-bpm`

这意味着当前后端主线不是“全家桶”，而是一个**模块化单体应用**，只装配了：

- 通用系统能力
- 基础设施能力
- BPM 工作流能力

### 2. `yudao-server` 是什么

[yudao-server/pom.xml](../../yudao-server/pom.xml:1) 写得很直白：它本质上是一个“空壳容器”。

它不负责业务实现，它负责：

- 引入业务模块依赖
- 组装成最终可运行的 Spring Boot 应用
- 打包成一个可启动的 jar

所以你要记住一个核心事实：

**`yudao-server` 是启动容器，不是业务模块。**

### 3. 启动入口在哪里

启动类只有一个：

[YudaoServerApplication.java](../../yudao-server/src/main/java/cn/iocoder/yudao/server/YudaoServerApplication.java:1)

它通过：

```java
@SpringBootApplication(scanBasePackages = {"${yudao.info.base-package}.server", "${yudao.info.base-package}.module"})
```

完成两件事：

1. 扫描 `server` 包下的启动层代码
2. 扫描 `module` 包下的业务模块代码

这说明系统采用的是**统一 Spring 上下文的模块化单体模式**。不是多个独立进程，不是多个 Spring Boot 服务，而是一个 JVM、一个应用上下文、多个业务模块。

## 二、整个项目的顶层架构：一张脑图先建立

你可以把项目理解成 4 层。

```text
前端层
  yudao-ui/yudao-ui-admin-vben-temp

接入与容器层
  yudao-server

业务模块层
  yudao-module-system
  yudao-module-infra
  yudao-module-bpm

基础框架层
  yudao-framework/*
  yudao-common
  各类 starter
```

更具体一点：

```text
HTTP / Token / Tenant / Exception / Response / MyBatis / Redis / MQ / Job / File / BPM
          ↑
     yudao-framework
          ↑
 system / infra / bpm
          ↑
      yudao-server
          ↑
        前端
```

理解这个分层之后，你才能判断一个问题该去哪里找：

- 请求路径前缀错了：先看 `framework-web`
- token 不生效：先看 `framework-security`
- SQL 被自动拼了 `tenant_id`：先看 `framework-tenant`
- 查询结果被做了数据权限过滤：先看 `framework-datapermission`
- 文件上传路径不对：看 `infra`
- 审批流状态不同步：看 `bpm`
- 用户角色菜单权限异常：看 `system`

## 三、为什么架构这么切：技术选型和设计意图

### 1. 为什么不是简单三层，而要加 `framework`

很多项目会把公共代码直接放在 `common` 或 `util`，最后所有模块都胡乱依赖。这个仓库没有这么做。

它选择了：

- `yudao-common`：最基础、最轻的公共对象和工具
- `yudao-framework/*`：按能力拆成多个 starter
- `yudao-module-*`：真正的业务模块

这是在做**能力分层**。

含义是：

- `common` 放“最不依赖业务、最稳定”的东西
- `framework` 放“技术基础设施能力”
- `module` 放“业务实现”

这是架构师视角里非常重要的一条：**不要把技术基础设施和业务代码混在一起。**

### 2. 为什么 `framework` 拆成很多 starter

当前 `yudao-framework` 下有这些主要子模块：

- `yudao-common`
- `yudao-spring-boot-starter-web`
- `yudao-spring-boot-starter-security`
- `yudao-spring-boot-starter-mybatis`
- `yudao-spring-boot-starter-biz-tenant`
- `yudao-spring-boot-starter-biz-data-permission`
- `yudao-spring-boot-starter-redis`
- `yudao-spring-boot-starter-job`
- `yudao-spring-boot-starter-mq`
- `yudao-spring-boot-starter-excel`
- `yudao-spring-boot-starter-monitor`
- `yudao-spring-boot-starter-protection`
- `yudao-spring-boot-starter-websocket`

这不是为了“好看”，而是为了做到：

- 能力模块化
- 依赖边界清晰
- 以后某个业务模块只引入需要的能力
- 未来如果拆服务，starter 可以直接复用

这就是**面向能力组装系统**，而不是面向目录凑代码。

### 3. 为什么是模块化单体，而不是微服务

当前代码的真实结构说明，它是标准的模块化单体：

- 一个启动入口
- 一个 Spring Boot 应用
- 多个 Maven 子模块
- 统一数据库和统一上下文

这么做的优点：

- 开发和调试成本低
- 模块之间调用简单，直接 Java API
- 事务处理简单
- 部署复杂度低

缺点：

- 强依赖同一个进程
- 上下文较大，启动重
- 模块间若边界不守，就会逐渐耦合

所以这套架构的核心不是“天然低耦合”，而是**靠模块边界和编码纪律维持低耦合**。

## 四、构建与依赖体系：Maven 这层是怎么设计的

### 1. 根 `pom` 的职责

[pom.xml](../../pom.xml:1) 负责：

- 聚合模块
- 统一版本号 `revision`
- 统一 Java 版本
- 统一 Maven 插件版本
- 导入依赖管理 BOM `yudao-dependencies`

这属于 Maven 的**父工程 + 依赖管理**模式。

### 2. `yudao-dependencies` 的价值

虽然你这轮没让我逐个展开 `yudao-dependencies`，但从根 `pom` 看得出它是 BOM。

它的目的不是写业务，而是：

- 锁死依赖版本
- 避免各模块各自升级包版本造成冲突
- 让所有模块只写 `artifactId`，不反复写版本

这是大型 Java 多模块工程的标准做法。

### 3. 版本选择的信号

根 `pom` 里能看到：

- `java.version=1.8`
- `spring.boot.version=2.7.18`
- `mapstruct.version=1.6.3`
- `lombok.version=1.18.42`

这反映出当前项目的设计取向是：

- **兼容性优先**
- **企业交付优先**
- **稳定生态优先**

不是追最新，而是追可控。

## 五、启动和配置系统：系统是怎么被装起来的

### 1. `application.yaml` 不是只放配置，它反映了整个运行模型

[application.yaml](../../yudao-server/src/main/resources/application.yaml:1) 暴露了很多系统设计事实。

比如：

- `spring.profiles.active=local`：当前默认跑本地环境
- `allow-circular-references=true`：系统接受部分循环依赖现实
- `multipart`：系统支持统一文件上传
- `springdoc` / `knife4j`：接口文档内建
- `flowable.database-schema-update=true`：Flowable 可以在启动时自动调整表结构
- `mybatis-plus`：开启驼峰映射、逻辑删除、别名包扫描
- `cache.type=REDIS`：缓存默认落 Redis

这说明项目不是裸 Spring Boot，而是已经把：

- API 文档
- BPM 引擎
- Redis 缓存
- MyBatis Plus
- 文件上传
- 多环境 profile

全当成一等公民了。

### 2. API 前缀是怎么统一出来的

[WebProperties.java](../../yudao-framework/yudao-spring-boot-starter-web/src/main/java/cn/iocoder/yudao/framework/web/config/WebProperties.java:1) 定义了：

- `appApi` 默认前缀 `/app-api`
- `adminApi` 默认前缀 `/admin-api`

[YudaoWebAutoConfiguration.java](../../yudao-framework/yudao-spring-boot-starter-web/src/main/java/cn/iocoder/yudao/framework/web/config/YudaoWebAutoConfiguration.java:1) 会根据 controller 所在包自动加前缀：

- `**.controller.admin.**` -> `/admin-api`
- `**.controller.app.**` -> `/app-api`

这是一种非常典型的“按包约定路由分层”的设计。

它的好处是：

- 避免每个 Controller 手写大前缀
- 接入层一眼能分辨管理端接口和应用端接口
- Nginx 代理规则更稳定

## 六、框架层详解：`yudao-framework` 到底在解决什么问题

### 1. `yudao-common`：最基础的底层契约

这个模块里最重要的不是工具类，而是系统级约定。

比如：

- [CommonResult.java](../../yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/pojo/CommonResult.java:1)
- [PageResult.java](../../yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/pojo/PageResult.java:1)
- [ErrorCode.java](../../yudao-framework/yudao-common/src/main/java/cn/iocoder/yudao/framework/common/exception/ErrorCode.java:1)

它们定义了全项目统一的：

- 返回格式
- 分页格式
- 错误码对象
- 异常体系

这不是语法细节，而是**全系统通信契约**。

如果没有这层统一约束，后面每个模块都会各自返回一套格式，接口会逐渐失控。

### 2. `framework-web`：把 Web 层标准化

[YudaoWebAutoConfiguration.java](../../yudao-framework/yudao-spring-boot-starter-web/src/main/java/cn/iocoder/yudao/framework/web/config/YudaoWebAutoConfiguration.java:1) 做了几件非常关键的事：

- 自动加 `/admin-api`、`/app-api` 前缀
- 注册全局异常处理器
- 注册统一响应包装器
- 注册跨域过滤器
- 注册请求体缓存过滤器
- 提供统一 `RestTemplate`

这是标准的“把 Web 基础设施从业务模块抽出去”的设计。

### 3. 全局异常处理：为什么 Controller 里不写 try/catch

[GlobalExceptionHandler.java](../../yudao-framework/yudao-spring-boot-starter-web/src/main/java/cn/iocoder/yudao/framework/web/core/handler/GlobalExceptionHandler.java:1) 负责把各种异常统一翻译成 `CommonResult`。

它处理的异常包括：

- 参数缺失
- 参数类型错误
- `@Valid` 校验错误
- `BindException`
- 上传文件过大
- 404、405
- `ServiceException`
- `AccessDeniedException`
- 未知异常

这套设计的意义是：

- 业务代码只关心抛业务异常
- Web 层统一把异常翻译成前端可消费结果
- Filter 中抛异常也能走同一套翻译逻辑

### 4. `framework-security`：鉴权是如何接入的

核心配置类是：

[YudaoWebSecurityConfigurerAdapter.java](../../yudao-framework/yudao-spring-boot-starter-security/src/main/java/cn/iocoder/yudao/framework/security/config/YudaoWebSecurityConfigurerAdapter.java:1)

它做的事情包括：

- 关闭 Session
- 启用 CORS
- 禁用 CSRF
- 使用无状态 token 鉴权
- 注册统一认证失败与权限失败处理器
- 识别 `@PermitAll`
- 合并各模块自定义授权规则
- 兜底要求所有请求认证
- 在用户名密码过滤器前插入 token 过滤器

这说明项目的安全模型是：

**不是 Session 登录，不是服务端保存会话，而是 token 驱动的无状态鉴权。**

### 5. Token 是如何生效的

[TokenAuthenticationFilter.java](../../yudao-framework/yudao-spring-boot-starter-security/src/main/java/cn/iocoder/yudao/framework/security/core/filter/TokenAuthenticationFilter.java:1) 的职责是：

1. 从请求头或参数中取 token
2. 通过 `OAuth2TokenCommonApi` 校验 token
3. 构建 `LoginUser`
4. 放入 Spring Security 上下文
5. 让后续 `@PreAuthorize`、`getLoginUserId()` 等逻辑可用

这就是“用户态”进入后端的关键链路。

### 6. `framework-mybatis`：为什么数据库访问被统一封装

[YudaoMybatisAutoConfiguration.java](../../yudao-framework/yudao-spring-boot-starter-mybatis/src/main/java/cn/iocoder/yudao/framework/mybatis/config/YudaoMybatisAutoConfiguration.java:1) 负责：

- `@MapperScan`
- 注册分页插件
- 注册自动填充处理器
- 根据数据库类型选择主键生成器
- 统一 JSON TypeHandler

[BaseDO.java](../../yudao-framework/yudao-spring-boot-starter-mybatis/src/main/java/cn/iocoder/yudao/framework/mybatis/core/dataobject/BaseDO.java:1) 则定义了所有表默认共享的字段：

- `createTime`
- `updateTime`
- `creator`
- `updater`
- `deleted`

[BaseMapperX.java](../../yudao-framework/yudao-spring-boot-starter-mybatis/src/main/java/cn/iocoder/yudao/framework/mybatis/core/mapper/BaseMapperX.java:1) 把分页、批量插入、条件查询、连表查询等常用能力做成统一基类。

这套设计的核心价值是：

- 把重复 CRUD 能力抽到统一基类
- 避免每个 Mapper 反复写模板代码
- 用统一约束控制分页、逻辑删除、排序和 Join 查询

### 7. 多租户是怎么进来的

多租户入口主要在：

- [YudaoTenantAutoConfiguration.java](../../yudao-framework/yudao-spring-boot-starter-biz-tenant/src/main/java/cn/iocoder/yudao/framework/tenant/config/YudaoTenantAutoConfiguration.java:1)
- [DataPermission.java](../../yudao-framework/yudao-spring-boot-starter-biz-data-permission/src/main/java/cn/iocoder/yudao/framework/datapermission/core/annotation/DataPermission.java:1)

`tenant` 做的是“租户隔离”。

它包含：

- 从请求中解析 `tenant-id`
- 放入租户上下文
- 在 MyBatis 拦截器里自动拼接租户条件
- 在缓存 key 上自动拼租户后缀
- 在 MQ、Job 场景里传播租户信息

它解决的问题是：

**同一套系统服务多个租户，但默认 SQL、缓存、消息、任务都不能串租户。**

### 8. 数据权限与多租户的区别

很多人会混淆。

- 多租户：控制“你属于哪个公司”
- 数据权限：控制“你在公司里能看哪些数据”

`@DataPermission(enable = false)` 在很多关键方法上出现，是因为有些查询必须绕过数据权限，否则会递归、查不到人、查不到部门或查权限本身。

这是典型的高级系统问题：**权限系统本身不能被权限系统错误地拦死。**

## 七、业务模块层：`system`、`infra`、`bpm` 是如何分工的

### 1. `system`：系统级业务底座

[yudao-module-system/pom.xml](../../yudao-module-system/pom.xml:1) 描述得很准：它存放支撑上层核心业务的通用业务。

它的目录结构可以分成几类：

- `controller/admin`：管理后台接口
- `controller/app`：应用端接口
- `service/*`：业务服务
- `dal/dataobject`：表对象
- `dal/mysql`：Mapper
- `api/*`：给其他模块调用的系统接口
- `framework/*`：仅 system 模块自己需要的框架扩展
- `mq/*`：消息生产与消费
- `job/*`：定时任务

它负责的核心能力有：

- 认证登录
- 用户、部门、岗位、角色、菜单、权限
- 字典
- OAuth2 token
- 短信
- 邮件
- 通知
- 社交登录
- 租户管理
- 登录日志、操作日志等

这是典型的“平台系统模块”。

### 2. `infra`：基础设施与研发工具

[yudao-module-infra/pom.xml](../../yudao-module-infra/pom.xml:1) 定义了两块职责：

1. 运维与管理基础设施
2. 提升研发效率与质量的工具

你看它的目录就能判断出这件事：

- `codegen`：代码生成
- `config`：配置中心
- `db`：数据源与数据库表结构
- `file`：文件管理
- `job`：定时任务管理
- `logger`：访问日志、错误日志
- `redis`：Redis 观测
- `websocket`：WebSocket 能力
- `monitor`：监控集成

它不是一个“业务模块”，而是一个“平台运营与工具模块”。

### 3. `bpm`：工作流与审批

[yudao-module-bpm/pom.xml](../../yudao-module-bpm/pom.xml:1) 已经说明：

- 流程定义
- 流程表单
- 审核中心
- 流程实例
- 流程任务

它是基于 Flowable 6 的业务流程模块。

内部又可以分成：

- `definition`：流程定义、表单、用户组、监听器、表达式
- `task`：流程实例、任务审批、抄送、退回、转办、加签
- `api`：提供给别的业务模块发起流程
- `framework/flowable`：Flowable 深度扩展
- `oa`：示例业务，请假单

`oa` 不是重点业务模块，它是 BPM 接入样板。

## 八、请求从浏览器进来到数据库落地：完整生命周期

### 1. 路由分发

请求打到后端之后，先通过 `framework-web` 自动加的前缀识别进入：

- `/admin-api/**`
- `/app-api/**`

### 2. Web 过滤器阶段

常见会经过：

- CORS 过滤器
- RequestBody 缓存过滤器
- 租户上下文过滤器
- 租户安全过滤器
- Token 认证过滤器

### 3. 安全与登录用户注入

`TokenAuthenticationFilter` 校验 token 后，会把 `LoginUser` 放进安全上下文。后续 Controller 和 Service 才能通过工具方法拿到当前登录人。

### 4. Controller 接参数

Controller 只做：

- 接口路由
- 参数校验
- 权限声明
- 调 Service
- 返回 `CommonResult`

### 5. Service 执行业务

Service 是真正的业务编排层。

它会做：

- 参数和状态校验
- 事务控制
- 调用 Mapper
- 调用其他模块 API
- 发布事件
- 调用 MQ、Redis、文件、流程引擎

### 6. Mapper 与数据库

Mapper 通过 `BaseMapperX` 获得统一分页和查询能力，实体通过 `BaseDO` 获得统一审计字段和逻辑删除字段。

### 7. 返回结果

正常结果统一包装成 `CommonResult.success(data)`。

异常则交给 `GlobalExceptionHandler` 翻译成统一错误码和消息。

## 九、三条最值得你反复走读的主链路

### 1. 登录链路

推荐你按这条链路反复读：

- [AuthController.java](../../yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/controller/admin/auth/AuthController.java:1)
- [AdminAuthServiceImpl.java](../../yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/service/auth/AdminAuthServiceImpl.java:1)
- [OAuth2TokenServiceImpl.java](../../yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/service/oauth2/OAuth2TokenServiceImpl.java:1)
- [TokenAuthenticationFilter.java](../../yudao-framework/yudao-spring-boot-starter-security/src/main/java/cn/iocoder/yudao/framework/security/core/filter/TokenAuthenticationFilter.java:1)

这条链路教你：

- 登录不是 Security 默认 form login
- token 如何创建
- token 如何持久化到 MySQL 和 Redis
- token 如何在后续请求里恢复成 `LoginUser`
- 登录日志如何记录

### 2. 文件链路

推荐你按这条链路走：

- [FileController.java](../../yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/controller/admin/file/FileController.java:1)
- [FileServiceImpl.java](../../yudao-module-infra/src/main/java/cn/iocoder/yudao/module/infra/service/file/FileServiceImpl.java:1)

这条链路教你：

- 后端直传与前端预签名直传两种上传模式
- 文件路径生成规则
- 文件元数据为什么要单独存库
- 文件存储为什么通过 `FileClient` 抽象适配本地、S3、OSS、SFTP

### 3. BPM 链路

推荐你按这条链路走：

- [BpmOALeaveController.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/controller/admin/oa/BpmOALeaveController.java:1)
- [BpmOALeaveServiceImpl.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/oa/BpmOALeaveServiceImpl.java:1)
- [BpmProcessInstanceApi.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/api/task/BpmProcessInstanceApi.java:1)
- [BpmProcessInstanceServiceImpl.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/task/BpmProcessInstanceServiceImpl.java:1)
- [BpmFlowableConfiguration.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/framework/flowable/config/BpmFlowableConfiguration.java:1)
- [BpmOALeaveStatusListener.java](../../yudao-module-bpm/src/main/java/cn/iocoder/yudao/module/bpm/service/oa/listener/BpmOALeaveStatusListener.java:1)

这条链路教你：

- 业务单据和流程实例如何解耦
- `businessKey` 为什么是 BPM 落地的核心
- Flowable 为什么要做自定义行为工厂和监听器
- 流程结束时为什么通过 Spring 事件回写业务状态

## 十、SQL 初始化脚本的意义：不是只拿来建表

`sql/mysql/ruoyi-vue-pro.sql` 不只是建表脚本，它还是系统的“默认元数据装配脚本”。

里面除了 `CREATE TABLE`，还有大量：

- 字典数据
- 菜单数据
- 默认配置
- 文件存储配置示例
- 定时任务示例

例如：

- `infra_file_config` 里放了多种文件存储配置示例
- `system_dict_type` 和 `system_dict_data` 里放了字典体系
- `system_menu` 里放了菜单与权限点

这意味着：

**数据库不是纯粹的数据容器，它同时也是部分系统元配置的承载体。**

## 十一、前端在整个仓库里的位置

`yudao-ui` 下当前保留的管理后台前端实现是：

- `yudao-ui-admin-vben-temp`

这里进一步收敛到 `Vue 3 + TypeScript + Vite + Pinia + Vue Router + Element Plus + Vben Admin` 这一条主线。

这说明当前工作区里的后端接口，主要就是围绕这一套管理后台来组织和验证。

所以后端接口设计强调：

- `CommonResult`
- `PageResult`
- 统一前缀
- 字典、菜单、权限、租户等标准化

这是典型的平台后端思路。

## 十二、这套仓库里最重要的 Java 八股知识清单

这里不是面试背诵版，而是“在当前仓库里真实有用”的知识点。

### 1. IOC / DI

没有 IOC，你根本读不懂这套项目。几乎所有业务都是通过 Spring 注入装配的。

你要熟悉：

- `@Service`
- `@Component`
- `@Configuration`
- `@Bean`
- `@Resource`
- `@Lazy`
- 自动配置 `@AutoConfiguration`

### 2. AOP

这里 AOP 不只是日志。

它被用于：

- 数据权限
- 租户忽略
- 操作日志
- Job 多租户执行

如果你不懂 AOP，就会误以为“明明业务代码没写租户条件，为什么 SQL 被改了”。

### 3. 事务

重点掌握：

- `@Transactional`
- 回滚边界
- 为什么业务落库和流程发起必须一个事务
- 为什么 token 创建与刷新也要事务化

### 4. ThreadLocal 上下文

你不需要直接手写很多 ThreadLocal，但必须理解系统里有两类关键上下文：

- 登录用户上下文
- 租户上下文

这决定了为什么后续 Service 和 Mapper 能“不显式传参”也知道是谁、属于哪个租户。

### 5. 设计模式

这套代码里真实能看到的模式有：

- 门面模式：`BpmProcessInstanceApi`
- 模板/基类复用：`BaseMapperX`、`BaseDO`
- 观察者模式：BPM 状态事件
- 策略模式：BPM 审批候选人策略
- 适配器模式：不同文件存储客户端
- 配置装配模式：各类 starter auto-configuration

### 6. DTO / VO / DO 分层

这是整个仓库的核心编码风格。

- `DO` 面向数据库
- `VO` 面向 HTTP
- `DTO` 面向模块内或模块间传输
- `Convert` 层做对象转换

你如果直接把 DO 暴露给前端，等于在破坏整个项目的基本设计。

### 7. 泛型与统一返回

`CommonResult<T>`、`PageResult<T>` 是全项目接口契约的一部分。

这是典型的泛型在企业项目里的真实用法。

### 8. 枚举和错误码体系

项目大量使用：

- 状态枚举
- 字典类型枚举
- 错误码常量

这说明它很强调：

- 状态语义明确
- 错误可定位
- 前后端协作稳定

### 9. ORM 不是 JPA，而是 MyBatis Plus

为什么选 MyBatis Plus：

- SQL 可控
- 适合复杂条件拼接
- 多租户和数据权限拦截器好接
- 比 JPA 更贴近中国企业项目的开发习惯

它的代价是：

- 需要更强的 SQL 与对象映射意识
- Join、多表和复杂查询需要自己设计清楚

### 10. 事件驱动

Spring Event 在这里不是装饰，而是业务解耦手段。

典型例子就是 BPM 审批状态回写。

## 十三、架构设计上的优点与代价

### 1. 优点

- 模块边界比较清晰
- 基础设施能力抽离得比较彻底
- 多租户、数据权限、认证、异常处理、统一返回、文件存储、BPM 都是体系化设计
- 对中国企业后台项目非常实用
- 代码生成器可以显著降低 CRUD 成本

### 2. 代价

- 上下文较重，学习成本高
- 自动装配、过滤器、拦截器、AOP 很多，新人一开始容易找不到真实执行路径
- 多租户、数据权限、Redis、MQ、Flowable 叠在一起时，问题排查复杂
- `allow-circular-references=true` 说明现实里已有一定复杂依赖
- 模块化单体如果边界守不住，会慢慢退化成“大泥球”

## 十四、如何像高级程序员一样读这套仓库

不要按文件名随机读。建议按下面顺序。

### 第一轮：启动与基础设施

1. [pom.xml](../../pom.xml:1)
2. [yudao-server/pom.xml](../../yudao-server/pom.xml:1)
3. [YudaoServerApplication.java](../../yudao-server/src/main/java/cn/iocoder/yudao/server/YudaoServerApplication.java:1)
4. [application.yaml](../../yudao-server/src/main/resources/application.yaml:1)
5. `framework-web / security / mybatis / tenant`

目标：知道系统怎么启动、怎么接请求、怎么鉴权、怎么查数据库。

### 第二轮：系统底座业务

1. `AuthController`
2. `AdminAuthServiceImpl`
3. `OAuth2TokenServiceImpl`
4. 用户、角色、菜单、权限服务

目标：知道“人”是怎么进入系统并被授权的。

### 第三轮：基础设施能力

1. `FileController` / `FileServiceImpl`
2. `CodegenServiceImpl`
3. Job、Config、Logger

目标：知道平台能力如何服务业务。

### 第四轮：BPM

1. `BpmProcessInstanceController`
2. `BpmTaskServiceImpl`
3. `BpmProcessInstanceServiceImpl`
4. `OA 请假` 示例

目标：知道“业务单据 + 工作流引擎”如何真正耦合。

## 十五、如果你以后要在这个仓库里加新功能，应该怎么判断落点

### 1. 先判断它属于哪类

- 用户、权限、登录、菜单、字典：放 `system`
- 文件、配置、任务、日志、代码生成：放 `infra`
- 审批流、流程定义、待办、流程实例：放 `bpm`
- 完全新的业务域：新建 `yudao-module-xxx`

### 2. 再判断它依赖哪些框架能力

- 需要认证：依赖 `security`
- 需要租户：依赖 `tenant`
- 需要数据权限：依赖 `biz-data-permission`
- 需要数据库：依赖 `mybatis`
- 需要导入导出：依赖 `excel`
- 需要审批：调用 `bpm api`

### 3. 然后按统一分层落代码

- `controller`
- `service`
- `dal/dataobject`
- `dal/mysql`
- `convert`
- `enums`
- 必要时 `api`

## 十六、想达到架构师水准，你真正要掌握的不是“记住目录”，而是这 10 个判断

1. 这个类是业务类，还是框架类，还是装配类。
2. 这个功能是应该依赖已有模块，还是应该新建模块。
3. 这个状态应该存业务表，还是只存流程引擎。
4. 这个权限问题是认证、租户、数据权限，还是菜单权限。
5. 这个配置应该放 YAML、数据库配置表，还是代码常量。
6. 这个能力是系统底座能力，还是某个业务域的私有能力。
7. 这个逻辑应该写在 Controller、Service、Mapper、Filter、Listener、AOP 里的哪一层。
8. 这个异常应该转成业务错误码，还是直接抛系统异常。
9. 这个功能应该同步执行、异步执行，还是事件驱动。
10. 这个需求是“加代码”，还是“先找清楚当前链路在哪一层”。

如果这 10 个判断你都能稳定做对，你就不是“会写增删改查”，而是真正开始具备高级程序员和架构师的代码感了。

## 十七、最后给你的仓库总判断

当前仓库的后端主线，是一个**强工程化、强平台化、模块化单体**的企业后台架构。

它的核心价值不在于“代码很新”，而在于：

- 分层明确
- 能力完整
- 适合持续长线演化
- 适合做中后台、审批、平台、基础设施型业务

它真正难的地方也不在 Java 语法，而在于：

- 横切能力太多
- 上下文切面多
- 模块边界要靠纪律守住
- 新功能必须按体系接入，而不能随便写

你要是按这份文档给出的阅读顺序去走，并且反复跟着三条主链路读代码，这个仓库你就不再只是“看得懂”，而是会开始知道它为什么这么设计、哪里能改、哪里不能乱碰。
