"""把普通子 Agent 的真实 executor 结果转换成根图可验证的完成回执。"""

from __future__ import annotations

from hashlib import sha256
from typing import NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, ToolMessage

from ..orchestration.delegated_receipt import (
    draft_receipt_from_tool_response,
    execution_receipt_from_tool_response,
    project_investigation_receipt_from_tool_messages,
)
from ..orchestration.domain_dispatch import parse_work_order
from ..tools.common import ToolResponse
from ..tools.common.events import current_agent_context


class ExecutionReceiptState(AgentState):
    """DeepAgents 使用 structured_response 把代码拥有的结果传回 task。"""

    structured_response: NotRequired[dict[str, object]]


class ExecutionReceiptMiddleware(AgentMiddleware):
    """发布代码拥有的领域回执。

    普通 WorkOrder 仍只读取唯一 executor；``project.investigate`` 则汇总本次
    项目调查的全部真实 ToolResponse，避免把子 Agent 最后一段自然语言当成事实。
    最后一段自然语言可以单独作为受限展示文本回传，但绝不进入事实、权限或导出
    文件的判定。
    ``project.list`` 是进入项目调查前的确定性定位查询，不需要让子 Agent 用
    ReAct 再判断一次唯一执行器，因此由本中间件直接签发并在结果返回后结束。
    """

    name = "ExecutionReceiptMiddleware"

    def __init__(self, *, skip_tools: frozenset[str] = frozenset()) -> None:
        self._skip_tools = skip_tools

    @staticmethod
    def _work_order(state):
        for message in reversed((state or {}).get("messages") or []):
            content = getattr(message, "content", "")
            if isinstance(message, dict):
                content = message.get("content", "")
            work_order = parse_work_order(str(content or ""))
            if work_order is not None:
                return work_order
        return None

    @classmethod
    def _project_investigation_receipt(cls, state):
        """读取当前项目调查已经获得的确定性回执。

        参数：
            state：项目子 Agent 当前回合的消息状态。

        返回：至少完成过一次项目业务工具调用时的强类型回执；尚无事实或当前
        WorkOrder 不是 ``project.investigate`` 时返回 ``None``。

        事实回执始终只从 ToolResponse 构造。项目子 Agent 的自由文本既不进入
        回执，也不被主 Agent 转交：项目分析、资料目录和导出结果都可以从这一
        组已验证事实确定性呈现；需要解释资料语义时，由主 Agent 只基于压缩后的
        引用事实生成答复。
        """
        work_order = cls._work_order(state)
        if not (
            work_order is not None
            and work_order.domain == "project"
            and work_order.action == "project.investigate"
        ):
            return None
        return project_investigation_receipt_from_tool_messages(
            list((state or {}).get("messages") or []),
            plan_id=work_order.plan_id,
            project_id=str(work_order.canonical_plan.get("project_id") or ""),
        )

    @classmethod
    def _project_investigation_can_finish(cls, state) -> bool:
        """判断项目子 Agent 能否在已有事实后直接结束本次 ReAct。

        ``analyze_project`` 已由 Java 在同一时刻确定性计算项目 KPI、风险、成员
        进度、活动和资料状态。资料目录、任务和动态的查询同样是结构化事实，完成
        用户明确要求的范围后再让子 Agent 写一段自由文本不会增加任何事实，反而会
        多一次模型等待，并可能把内部字段带到用户界面。

        资料或制度检索也不例外。检索工具返回的命中片段已经是经过当前项目权限
        复核的证据，最终展示层只负责逐条引用，不再为了改写片段额外触发一次模型。
        否则子图已经结束、父图又进入自由 ReAct，既增加延迟，也可能重新打开无关
        文件系统工具或误造新的业务动作。文件交付由主图在最终正文提交后处理，
        不属于项目调查的完成条件。
        """

        work_order = cls._work_order(state)
        if not (
            work_order is not None
            and work_order.domain == "project"
            and work_order.action == "project.investigate"
        ):
            return False
        receipt = cls._project_investigation_receipt(state)
        if (
            receipt is None
            or receipt.status != "SUCCEEDED"
            or not receipt.facts.get("analyze_project")
        ):
            return False
        if any(item.status != "SUCCEEDED" for item in receipt.tool_trace):
            return False

        required_scope_tools = {
            "documents": "get_project_documents",
            "tasks": "get_project_tasks",
            "activity": "get_project_activity",
            "knowledge": "search_project_knowledge",
        }
        requested_scopes = {
            str(scope) for scope in (work_order.canonical_plan.get("requested_scopes") or ())
        }
        completed_tools = {item.tool for item in receipt.tool_trace}
        if any(tool not in completed_tools for tool in (
            required_scope_tools[scope]
            for scope in requested_scopes
            if scope in required_scope_tools
        )):
            return False
        # 附件由主 Agent 在取得这份完整事实回执后单独创建，领域子 Agent 不参与。
        return True

    @staticmethod
    def _project_list_call_id(plan_id: str) -> str:
        """Issue a Run-scoped id for the child graph's code-owned read call.

        The child graph normally starts with a fresh task state, but its tool
        messages are still durable protocol records.  A plan id is
        deterministic by design, so it cannot be the only correlation key
        when the same project list plan is requested in a later user turn.
        """

        context = current_agent_context()
        scope = str(context.get("runId") or context.get("messageId") or "local")
        digest = sha256(f"v1|project-list|{plan_id}|{scope}".encode("utf-8")).hexdigest()[:24]
        return f"compiled-project-list-{digest}"

    @classmethod
    def _direct_project_list_response(cls, state) -> AIMessage | None:
        """为已编译的项目列表 WorkOrder 直接调用唯一只读执行器。

        参数：
            state：项目子 Agent 的当前消息状态，首条 HumanMessage 中含主图签发的
                WorkOrder；该 WorkOrder 仍是工具、参数和项目访问范围的唯一事实源。

        返回：
            首次执行时返回 ``list_accessible_projects`` 工具调用；已经得到该工具的
            真实结果时返回空终态消息；其他领域或项目自主调查返回 ``None``，继续
            原有 ReAct 循环。

        设计说明：项目列表只用于把“这个项目”收敛为当前用户有权访问的项目编号，
        它没有需要模型补充或推理的业务分支。工具参数不在这里复制，而由
        ``WorkflowPlanBinderMiddleware`` 从 canonicalPlan 重填，Java 也会在调用
        时重新校验当前用户权限，因此直接执行不会扩大授权范围。
        """

        work_order = cls._work_order(state)
        if not (
            work_order is not None
            and work_order.domain == "project"
            and work_order.action == "project.list"
            and work_order.execution_tool == "list_accessible_projects"
        ):
            return None
        has_result = any(
            isinstance(message, ToolMessage)
            and str(message.name or "") == work_order.execution_tool
            for message in (state or {}).get("messages") or []
        )
        if has_result:
            return AIMessage(
                name="projects_agent",
                content="",
                response_metadata={"codeOwnedProjectListTerminal": True},
            )
        return AIMessage(
            name="projects_agent",
            content="",
            tool_calls=[{
                "name": work_order.execution_tool,
                # 具体分页参数只能由绑定中间件从 canonicalPlan 注入，不能在这里
                # 复制成第二份计划，也不能让模型自由填写。
                "args": {},
                "id": cls._project_list_call_id(work_order.plan_id),
                "type": "tool_call",
            }],
            response_metadata={"codeOwnedProjectListExecution": True},
        )

    def wrap_model_call(self, request, handler):
        """对确定性定位和已有项目事实跳过无效模型调用。"""

        state = getattr(request, "state", {}) or {}
        direct_project_list = self._direct_project_list_response(state)
        if direct_project_list is not None:
            return direct_project_list

        if self._project_investigation_can_finish(state):
            return AIMessage(
                name="projects_agent",
                content="",
                response_metadata={"codeOwnedProjectInvestigationTerminal": True},
            )
        return handler(request)

    async def awrap_model_call(self, request, handler):
        state = getattr(request, "state", {}) or {}
        direct_project_list = self._direct_project_list_response(state)
        if direct_project_list is not None:
            return direct_project_list
        if self._project_investigation_can_finish(state):
            return AIMessage(
                name="projects_agent",
                content="",
                response_metadata={"codeOwnedProjectInvestigationTerminal": True},
            )
        return await handler(request)

    def after_agent(self, state, runtime):
        work_order = self._work_order(state)
        if work_order is None or work_order.execution_tool in self._skip_tools:
            return None
        if work_order.domain == "project" and work_order.action == "project.investigate":
            receipt = self._project_investigation_receipt(state)
            return (
                {"structured_response": receipt.model_dump(by_alias=True, exclude_none=True)}
                if receipt is not None else None
            )
        messages = [
            message for message in (state.get("messages") or [])
            if isinstance(message, ToolMessage)
            and str(message.name or "") == work_order.execution_tool
        ]
        # 一个 WorkOrder 只能产生一个 terminal executor 结果，避免从历史中
        # 猜测“哪一次才算成功”。helper 和拒绝 ToolMessage 都不会进入这里。
        if len(messages) != 1:
            return None
        try:
            result = ToolResponse.model_validate_json(str(messages[0].content or ""))
        except (TypeError, ValueError):
            return None
        # 写工作流先尝试生成领域级草稿回执。只有该回执才有资格在父图触发
        # HITL；其他成功结果仍严格使用通用执行回执。
        receipt = draft_receipt_from_tool_response(
            result,
            domain=work_order.domain,
            operation=str(work_order.canonical_plan.get("operation") or ""),
        ) or execution_receipt_from_tool_response(
            result, plan_id=work_order.plan_id, executor_tool=work_order.execution_tool,
        )
        # 省略空字段，使跨图回执只承载真实 executor 返回的业务事实；这也让
        # “字段不存在”和“字段值为 null”在主图侧保持明确区分。
        return {"structured_response": receipt.model_dump(by_alias=True, exclude_none=True)}

    async def aafter_agent(self, state, runtime):
        return self.after_agent(state, runtime)


__all__ = ["ExecutionReceiptMiddleware", "ExecutionReceiptState"]
