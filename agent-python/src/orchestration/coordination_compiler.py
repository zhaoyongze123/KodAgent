"""跨领域请求的批次编译边界。

文件职责
========
模型只能提交多个“候选动作 + 候选字段”，本模块逐项复用既有 ``compile_plan``，
并将每个已解析结果变成独立 WorkOrder。它不执行任务，也不从某一步的结果自动
拼出另一步的业务字段。

第一期只签发相互独立的只读查询与草稿准备步骤。真正依赖上一步业务结果的链路
（例如“先查日程再修改第一个”）仍使用现有候选定位与 Java 二次核验路径；不能
把未实现的结果绑定伪装成通用 DAG 功能。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.coordination import CoordinationBatch, CoordinationStep
from ..domain.plan import ExecutionClass
from .capabilities import action_read_only, resolve_action
from .compiler import compile_plan
from .domain_dispatch import WorkOrder, serialize_work_order, work_order_from_compiled_plan


class CoordinationCandidateStep(BaseModel):
    """模型提议的一项跨领域子任务，尚不包含执行器或业务 ID。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64)
    capability_id: str = Field(min_length=1, max_length=64)
    action_id: str = Field(min_length=1, max_length=128)
    execution_class: ExecutionClass
    candidate_plan: dict[str, Any] = Field(default_factory=dict)
    query_intent: dict[str, Any] = Field(default_factory=dict)
    failure_policy: Literal["CONTINUE", "BLOCK_DEPENDENTS"] = "CONTINUE"


class CoordinationCompilationError(ValueError):
    """任一子步骤未能通过中央编译，整批不能派发。"""


def compile_coordination_batch(
    steps: list[CoordinationCandidateStep],
    *,
    tenant_id: str,
    user_id: str,
    thread_id: str,
    run_id: str,
    origin_run_id: str | None = None,
    message_id: str,
    user_context: str | None = None,
) -> CoordinationBatch:
    """编译一组独立步骤为可持久化协作批次。

    所有步骤必须解析为既有 Action Catalog 中的 RESOLVED WorkOrder。第一期不允许
    ``depends_on``：只有在实现“上一步结构化事实 -> 下一步受限字段绑定”后，才会
    开放真正的跨步骤数据依赖，避免将结果文本误当成业务事实。
    """

    if not 2 <= len(steps) <= 4:
        raise CoordinationCompilationError("跨领域批次当前要求包含 2 到 4 个独立步骤")
    if len({step.step_id for step in steps}) != len(steps):
        raise CoordinationCompilationError("跨领域批次的 step_id 不能重复")

    compiled_steps: list[CoordinationStep] = []
    seen_domains: set[str] = set()
    write_step_id: str | None = None
    for index, proposal in enumerate(steps, start=1):
        # 同一领域多个步骤通常存在先后事实依赖，第一期不能靠并发碰运气。
        if proposal.capability_id in seen_domains:
            raise CoordinationCompilationError("第一期批次每个领域最多一个独立步骤")
        seen_domains.add(proposal.capability_id)
        # action_id 是步骤协议的显式字段。它仍会由 compile_plan 按当前领域
        # Action Catalog 验证；这里仅把运输层字段放回单领域编译器已有的输入形状，
        # 不允许模型借 candidate_plan 隐藏或替换动作。
        candidate_plan = dict(proposal.candidate_plan)
        candidate_plan["action_id"] = proposal.action_id
        compiled = compile_plan(
            capability_id=proposal.capability_id,
            execution_class=proposal.execution_class,
            candidate_plan=candidate_plan,
            query_intent=proposal.query_intent,
        )
        if compiled.status != "RESOLVED":
            reason = "；".join(compiled.issues or compiled.missing_fields) or "动作未能解析"
            raise CoordinationCompilationError(f"步骤 {proposal.step_id} 不能编译: {reason}")
        work_order = work_order_from_compiled_plan(
            compiled, user_context=user_context, revision=index,
        )
        if work_order is None:
            raise CoordinationCompilationError(f"步骤 {proposal.step_id} 的执行器契约不可用")
        action = resolve_action(work_order.domain, work_order.action)
        if action is None:
            # work_order_from_compiled_plan 已校验此条件；保留防御性检查，避免
            # 未来修改 WorkOrder 构造器时让批次绕过 Action Catalog。
            raise CoordinationCompilationError(f"步骤 {proposal.step_id} 的动作契约不可用")
        if not action_read_only(action):
            if write_step_id is not None:
                raise CoordinationCompilationError(
                    "第一期跨领域批次最多包含一个需确认的写操作；请拆分为两次请求。"
                )
            write_step_id = proposal.step_id
        compiled_steps.append(CoordinationStep(
            step_id=proposal.step_id,
            domain=work_order.domain,
            action_id=work_order.action,
            executor_tool=work_order.execution_tool,
            work_order=work_order.model_dump(by_alias=True, mode="json"),
            # 独立步骤即使失败也应汇总其余领域结果。
            failure_policy=proposal.failure_policy,
        ))

    return CoordinationBatch(
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        # 恢复 Run 仍属于最初那次用户请求。批次必须保存原始 Run，后续每个
        # Operation/HITL 才能按既有身份边界校验，而不能把恢复 Run 当成新请求。
        origin_run_id=str(origin_run_id or run_id),
        current_run_id=run_id,
        message_id=message_id,
        request_summary=user_context.strip()[:1000] if isinstance(user_context, str) and user_context.strip() else None,
        steps=tuple(compiled_steps),
    )


def batch_work_order_descriptions(batch: CoordinationBatch) -> tuple[str, ...]:
    """生成发送给子 Agent 的纯 WorkOrder 描述，不夹带自由执行指令。"""

    return tuple(
        serialize_work_order(
            # CoordinationStep 已由编译器写入同一 WorkOrder JSON；在本模块再次
            # 验证结构可避免将存储损坏数据传到 DeepAgents task 描述。
            WorkOrder.model_validate(step.work_order)
        )
        for step in batch.steps
    )


__all__ = [
    "CoordinationCandidateStep", "CoordinationCompilationError", "batch_work_order_descriptions",
    "compile_coordination_batch",
]
