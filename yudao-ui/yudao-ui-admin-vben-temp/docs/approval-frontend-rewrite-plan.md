# 审批系统前端重写方案

## 设计读法

Reading this as: 企业内部高频审批产品，面向长时间在线的员工、审批人和管理人员，采用接近 Linear / GitHub / Jira / 钉钉 OA 的高密度专业工作台语言，强调信息优先、流程优先、操作优先。

## 第一步：审批系统业务流程分析

### 1. 流程主链

基于当前仓库真实后端，审批系统的主链不是单一“表单提交”，而是四条并行能力：

1. 发起审批
2. 处理待办
3. 回看已办 / 我发起的 / 抄送我的
4. 流程管理与流程配置

### 2. 真实后端能力边界

当前后端来自 `yudao-module-bpm`，接口能力确认如下：

| 模块 | 真实接口能力 |
| --- | --- |
| 流程实例 | `/bpm/process-instance/my-page`、`/manager-page`、`/create`、`/get`、`/get-approval-detail`、`/get-next-approval-nodes`、`/get-bpmn-model-view`、`/get-print-data`、`/cancel-by-start-user`、`/cancel-by-admin` |
| 流程任务 | `/bpm/task/todo-page`、`/done-page`、`/manager-page`、`/approve`、`/reject`、`/return`、`/delegate`、`/transfer`、`/create-sign`、`/delete-sign`、`/copy`、`/withdraw` |
| 流程配置 | 分类、表单、模型、流程定义、表达式、监听器、用户组 |
| OA 申请单 | 请假、出差、加班、报销、考勤、用章、项目立项、人员调配、文件审批 |
| 基础能力 | 登录、刷新令牌、菜单权限、用户列表、字典、文件上传 |

### 3. 真实业务对象

OA 申请并不是一个统一表：

1. 通用 OA 类：`attendance`、`expense`、`overtime`、`trip`
2. 专门业务类：`leave`、`project`、`seal`、`staffing`、`document`
3. 平台通用流程：基于流程定义发起，可能是 `NORMAL` 流程表单，也可能是 `CUSTOM` 业务表单

### 4. 关键交互流

#### 4.1 员工发起

1. 选择流程分类
2. 选择具体流程定义
3. 填写表单 / 业务页面
4. 如流程要求，选择启动时指定审批人 `startUserSelectAssignees`
5. 提交流程实例

#### 4.2 审批人处理

1. 进入系统先看待办队列
2. 打开详情
3. 在同页查看申请信息、流程图、节点、历史、附件、可执行动作
4. 执行通过 / 驳回 / 退回 / 委派 / 转派 / 加签 / 减签 / 抄送

#### 4.3 发起人回看

1. 查看我发起的流程
2. 对运行中流程撤销
3. 对已结束流程重新发起
4. 查看打印数据和流转记录

#### 4.4 管理侧

1. 监管全局流程实例
2. 监管全局任务
3. 配置流程模型、流程表单、分类、表达式、监听器、用户组
4. 查看基于流程定义的报表

## 第二步：信息架构设计

### 1. 顶层信息域

重写后的系统拆成四个信息域：

1. 工作台
2. 发起
3. 流程资产
4. 系统配置

### 2. 信息组织原则

1. 把“我现在要处理什么”放在最前
2. 把“这条流程现在走到哪了”放在详情核心区
3. 把“筛选、列表、批量动作”放在列表页固定位置
4. 把“流程配置资产”与“业务处理工作区”彻底隔离

### 3. 页面对象模型

#### 3.1 工作对象

1. 待办任务
2. 已办任务
3. 我发起的流程
4. 抄送给我的流程

#### 3.2 资产对象

1. 流程定义
2. 流程模型
3. 流程表单
4. 流程分类
5. 用户组
6. 监听器
7. 表达式

#### 3.3 业务对象

1. 通用流程实例
2. OA 业务单据
3. 审批节点
4. 审批动作
5. 附件与打印

## 第三步：导航结构设计

### 1. 全局导航

采用“顶部主导航 + 左侧上下文导航 + 主区工作面板”的三段结构。

#### 顶部主导航

1. 工作台
2. 发起审批
3. 审批中心
4. 流程资产
5. 管理视图

### 2. 左侧上下文导航

#### 工作台

1. 待我处理
2. 紧急与超时
3. 最近处理
4. 我的发起
5. 抄送给我

#### 发起审批

1. 全部流程
2. 按分类浏览
3. 最近发起
4. 常用流程

#### 审批中心

1. 待办
2. 已办
3. 我发起的
4. 抄送我的

#### 流程资产

1. 流程模型
2. 流程定义
3. 流程表单
4. 流程分类
5. 用户组
6. 表达式
7. 监听器

#### 管理视图

1. 流程实例
2. 流程任务
3. 流程报表

### 3. 导航决策

1. 不做传统后台树形菜单堆满左侧
2. 主导航按任务域切分，不按技术模块切分
3. 高频用户只需要在“工作台”和“审批中心”来回切换
4. 管理配置能力单独收纳，避免污染审批工作流主界面

## 第四步：页面结构设计

### 1. 工作台首页

首页不是 Dashboard 卡片堆砌，而是一个审批收件箱。

#### 布局

1. 顶部：全局搜索、快速筛选、刷新、当前用户上下文
2. 主列：待办表格
3. 右列：紧急事项、超时事项、最近处理
4. 底部延展区：我发起的最近流程、抄送动态

### 2. 发起审批页

#### 布局

1. 顶部：流程搜索
2. 左侧：分类索引
3. 主区：流程定义列表
4. 右侧：当前流程摘要 / 最近使用 / 表单预览入口

说明：
不用大卡片宫格，改为高密度流程目录视图。每个流程定义一行，包含图标、名称、分类、摘要、发起按钮。

### 3. 审批中心列表页

#### 统一结构

1. 顶部工具带：状态切换、搜索、筛选、时间范围
2. 中部：表格
3. 右上角：批量操作与导出入口

#### 表格列优先级

1. 流程名称
2. 发起人
3. 当前节点
4. 状态
5. 紧急程度 / 超时标识
6. 创建时间
7. 已耗时
8. 操作

### 4. 审批详情页

详情页是系统核心页面，采用“三栏信息面”：

#### 左栏：申请内容

1. 表单正文
2. 业务字段
3. 附件
4. 发起补充信息

#### 中栏：流程状态

1. 当前状态条
2. 节点时间线
3. 当前节点说明
4. 下一节点预览
5. 流程图 / 简化图切换

#### 右栏：操作与上下文

1. 审批动作区
2. 审批意见
3. 可选审批人
4. 加签减签等高级动作
5. 打印 / 撤回 / 重新发起 / 取消

### 5. 资产管理页

流程模型、定义、表单、分类、用户组、表达式、监听器统一采用：

1. 顶部说明条
2. 筛选和搜索工具带
3. 数据表格
4. 右侧抽屉编辑

说明：
管理页仍然是表格主导，但视觉语言与审批页一致，避免切成另一套老后台。

## 第五步：组件体系设计

### 1. 基础布局组件

1. `AppShell`
2. `TopNav`
3. `ContextRail`
4. `WorkSurface`
5. `PageHeader`
6. `SplitPane`

### 2. 审批领域组件

1. `ApprovalInboxTable`
2. `ApprovalStatusBadge`
3. `ApprovalUrgencyMark`
4. `ApprovalActionBar`
5. `ApprovalTimeline`
6. `ApprovalFlowPreview`
7. `ApprovalDetailFormRenderer`
8. `ApprovalAttachmentList`
9. `ApprovalNextNodePanel`

### 3. 发起领域组件

1. `ProcessCatalogList`
2. `ProcessCategoryNav`
3. `ProcessQuickSearch`
4. `ProcessLaunchPanel`

### 4. 配置领域组件

1. `EntityTableShell`
2. `EntityToolbar`
3. `EntityEditorDrawer`
4. `FormFieldPreview`

### 5. 通用交互组件

1. `DataTable`
2. `FilterBar`
3. `SectionTabs`
4. `EmptyState`
5. `InlineStat`
6. `StickyActionPanel`
7. `FileUploadField`

## 第六步：设计决策与体验优化点

### 1. 为什么不用卡片后台

因为审批不是浏览型应用，而是处理型应用。高频用户需要连续扫描和连续操作，卡片会浪费垂直空间并切碎信息。

### 2. 为什么详情页三栏

审批动作天然需要同时看三类信息：

1. 申请内容
2. 流程上下文
3. 当前可执行动作

三栏能减少来回切标签和弹窗。

### 3. 为什么首页直接是待办收件箱

高频审批用户进入系统的第一目标不是“看统计”，而是“处理任务”。统计只作为辅助，不应占据主入口。

### 4. 关键体验优化

1. 所有列表保留键盘可扫描性，行高控制在企业软件合理密度
2. 待办行支持直接打开详情，不强制二次跳转
3. 审批动作区固定在详情页右侧，滚动时仍可见
4. 超时、紧急、加签、抄送通过标签和分隔线表达，不靠大色块
5. 表单字段权限继续遵守后端返回的 `formFieldsPermission`
6. `NORMAL` 与 `CUSTOM` 表单路径分流，绝不伪造统一表单渲染
7. 所有上传仍走现有 `/infra/file/*` 接口

## 第七步：完整前端项目架构

### 1. 技术栈

1. React
2. TypeScript
3. Vite
4. TailwindCSS
5. TanStack Query
6. Zustand

### 2. 应用目录

```text
apps/web-react-bpm
├── src
│   ├── app
│   │   ├── providers
│   │   ├── router
│   │   └── styles
│   ├── features
│   │   ├── auth
│   │   ├── approval-center
│   │   ├── approval-detail
│   │   ├── process-launch
│   │   ├── process-assets
│   │   └── admin-monitor
│   ├── entities
│   │   ├── process-instance
│   │   ├── task
│   │   ├── process-definition
│   │   ├── oa-record
│   │   └── user
│   ├── shared
│   │   ├── api
│   │   ├── ui
│   │   ├── lib
│   │   ├── config
│   │   └── types
│   └── widgets
│       ├── app-shell
│       ├── inbox
│       ├── process-catalog
│       └── detail-panels
```

### 3. 数据分层

1. `shared/api`：HTTP 客户端、鉴权、基础接口
2. `entities/*/api`：面向领域对象的接口定义
3. `features/*`：用户动作编排
4. `widgets/*`：跨页面组合 UI
5. `shared/ui`：纯展示与基础组件

### 4. 路由结构

```text
/
├── /login
├── /workspace
├── /launch
├── /center/todo
├── /center/done
├── /center/initiated
├── /center/copied
├── /detail/:processInstanceId
├── /assets/categories
├── /assets/forms
├── /assets/models
├── /assets/definitions
├── /assets/groups
├── /assets/expressions
├── /assets/listeners
├── /admin/instances
├── /admin/tasks
└── /admin/reports
```

### 5. 实现原则

1. 不复用旧 Vue 组件
2. 只复用真实接口协议与业务规则
3. 页面交互保持高密度、低装饰、强分隔
4. 所有缺失功能必须由真实接口支撑后再实现，不做假入口
