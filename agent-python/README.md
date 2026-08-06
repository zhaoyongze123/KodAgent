# KodAgent DeepAgents 控制台原型

这是重新接入 DeepAgents 的 OA Agent 原型，采用一个主 Agent 加多个业务子 Agent：

```text
OA 主 Agent
├── approvals_agent       审批查询
├── meeting_rooms_agent   会议室查询
├── schedules_agent       日历查询
└── party_files_agent     党务文件查询
```

Python 侧按职责拆分为：

```text
src/oa_agent_console.py   控制台输入、流式输出
src/oa_agent.py           主 Agent、子 Agent、提示词和注册
src/tools/
├── common/               认证、HTTP 客户端、事件
├── meeting/              会议室、参会人、冲突、草稿、预约
├── approval/             审批查询
├── schedule/             日历查询
└── party_files/          党务文件查询
skills/meeting-room-booking/SKILL.md
```

## 运行

```bash
cd /Users/mac/项目/kodagent/agent-python
uv sync
cp .env.example .env
# 编辑 .env，填写 OPENAI_API_KEY
uv run oa-agent-console
```

启动后会进入 Rich 交互式控制台。输入问题开始对话，输入 `exit` 或 `退出` 结束。
控制台会流式显示模型回答，并将工具调用显示为友好的进度状态，不直接输出工具原始 JSON。

## 当前链路

```text
用户问题
  ↓
DeepAgents 主 Agent
  ↓
list_my_pending_approvals Tool
  ↓
模型整理结果
  ↓
控制台逐段输出
```

Tool 按领域和职责拆分，公共认证、HTTP 和事件能力集中在 `common/`。审批、日历和党务文件 Tool 均通过 Java Agent Facade 查询真实业务数据。会议室 Agent 现在支持完整的预约流程：查询会议室、搜索参会人员、查询参会人员日历、检查冲突、生成预约草稿，以及用户明确确认后的正式提交。正式提交前不会写入业务系统。党务文件当前提供四个只读接口：分页查询、详情（记录已读）、附件元数据（记录预览/下载动作）和分类查询。Python Agent 不直连数据库，也不调用普通后台接口；附件二进制内容不会传给模型。
# LangGraph Server 本地开发

```bash
cd /Users/mac/项目/kodagent/agent-python
uv sync
uv run langgraph dev --config langgraph.json --host 127.0.0.1 --port 2024
```

服务启动后，Graph ID 为 `oa_agent`，访问 `http://127.0.0.1:2024`。

`agent-chat-ui` 本地配置：

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:2024
NEXT_PUBLIC_ASSISTANT_ID=oa_agent
NEXT_PUBLIC_AUTH_SCHEME=
```

这一阶段用于验证 LangGraph Thread、流式 Run 和 Interrupt。`langgraph dev` 是开发运行时，
不会使用下面配置的 PostgreSQL。需要可恢复的 PostgreSQL 运行时，使用项目中的
`kodagent Python LangGraph PostgreSQL 重启.sh`，它通过 `langgraph up` 启动 LangGraph API
容器；Java、Python Agent 代码仍然来自当前本地项目，不需要新增 Java 事件微服务：

```bash
cd /Users/mac/项目/kodagent
docker compose -f script/docker/docker-compose.yml up -d langgraph-postgres redis

cd agent-python
set -a && source .env && set +a
uv run langgraph up --config langgraph.json \
  --postgres-uri "${LANGGRAPH_POSTGRES_URI}" \
  --port 2024 --wait
```

控制台如果需要跨进程恢复，也使用同一个 PostgreSQL：

```bash
OA_AGENT_CHECKPOINTER=postgres \
LANGGRAPH_POSTGRES_URI=postgresql://langgraph:langgraph@127.0.0.1:15432/langgraph \
uv run oa-agent-console
```

不要再把 `OA_AGENT_CHECKPOINTER` 设置为 `memory`；它只适合临时单进程调试。

存储边界：

- PostgreSQL：LangGraph Thread、Checkpoint、Run 状态，以及 Java Agent 事件表中的长期过程记录。
- Redis：Agent 过程事件的实时 Stream、短期预约草稿、分布式锁和断线补读。
- Java OA：认证、权限、业务事务和最终业务事实，不由 Agent 直接写数据库。

生产环境仍需经过 Agent Gateway，再接入 OA SSO、权限和租户上下文；不要把
`OA_AGENT_API_KEY`、数据库连接串或 LangSmith Key 放到 `NEXT_PUBLIC_` 环境变量中。

## 部署后运行时验收

Java 是业务动作目录的权威来源。每个启用的 Run 在第一次模型解析前会用当前
OA 身份读取 `/agent/config/actions`，校验动作、字段、枚举、权限、确认边界和
跨字段 `constraints`；严格模式发现漂移会直接阻止本次 Run，不会使用过期的
Python 目录。会议/日程时间区间、更新非空、批量任务唯一性、金额条件成对等
结构校验由该契约统一解释，冲突、权限和状态仍由 Java/Workflow 负责。

本地 Java 进程必须使用 `local` profile，使它与 LangGraph 容器使用同一个
`OA_AGENT_API_KEY`。项目根目录的 `process-compose.yaml` 已固定这一启动边界。
重启后可执行只读验收：

```bash
cd /Users/mac/项目/kodagent
OA_AGENT_BASE_URL=http://127.0.0.1:48080 \\
OA_AGENT_API_KEY=kodagent-local-dev-only-20260721 \\
OA_AGENT_CONSOLE_DEV_MODE=true OA_AGENT_USER_ID=1 OA_AGENT_TENANT_ID=1 \\
OA_AGENT_ACTION_CATALOG_SYNC=true OA_AGENT_ACTION_CATALOG_STRICT=true \\
/Users/mac/项目/kodagent/agent-python/.venv/bin/python scripts/verify-agent-runtime.py
```

需要确认真实模型供应商也可加 `--model-call`；脚本只读取 OA 设置中的模型，
不会切换到环境变量模型或其他供应商。
