"""OA Agent 主图装配入口。

调用链：应用启动调用 ``build_agent`` -> 注册全部工具契约、领域子 Agent 与中间件
-> DeepAgents 创建主图。模型配置不在这里固定，而由 ``DynamicModelMiddleware``
按 Run 从 Java 设置服务解析；这里的 ChatOpenAI 仅用于满足建图类型要求，不能
作为后备模型调用。
"""

import os
from datetime import datetime

from deepagents.backends.utils import create_file_data
from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_openai import ChatOpenAI
from .tools.common import (
    AGENT_TIMEZONE,
    apply_tool_contracts,
)
from .runtime.model_runtime import DynamicModelMiddleware, RunLifecycleMiddleware
from .middleware import (
    MeetingApprovalAutoConfirmMiddleware,
    ApprovalBatchAutoConfirmMiddleware,
    ApprovalTaskAutoConfirmMiddleware,
    ApprovalRequestAutoConfirmMiddleware,
    MeetingApprovalResumeMiddleware,
    MeetingDraftIdempotencyMiddleware,
    MeetingPrepareFirstMiddleware,
    MeetingTaskCallGuardMiddleware,
    DeterministicWorkflowTaskGuardMiddleware,
    PartyFileApprovalAutoConfirmMiddleware,
    ToolAuditMiddleware,
)
from .services.meeting_approval import confirmation_description, prepare_confirmation_interrupt
from .services.personal_schedule_approval import (
    personal_schedule_confirmation_description,
    prepare_personal_schedule_confirmation,
)
from .services.approval_batch_approval import confirmation_description as approval_batch_confirmation_description, prepare_confirmation_interrupt as prepare_approval_batch_confirmation
from .services.approval_task_approval import confirmation_description as approval_task_confirmation_description, prepare_confirmation_interrupt as prepare_approval_task_confirmation
from .services.approval_request_approval import confirmation_description as approval_request_confirmation_description, prepare_confirmation_interrupt as prepare_approval_request_confirmation
from .services.party_file_approval import prepare_party_file_confirmation
from .middleware.personal_schedule_approval import PersonalScheduleApprovalArgsMiddleware
from .middleware.personal_schedule_approval_resume import PersonalScheduleApprovalResumeMiddleware
from .middleware.chain import build_middleware_chain
from .orchestration.phase_prompt import (
    MAIN_AGENT_COMMON_PROMPT,
    MainAgentPhasePromptMiddleware,
    main_agent_phase_instructions,
    main_agent_prompt_for_phase,
    classify_main_agent_phase,
    system_prompt,
)
from .orchestration.skill_registry import skill_registry
from .orchestration.plan_projection import PlanToolProjectionMiddleware
from .orchestration.policies import (
    CurrentUserMessageMiddleware,
    MEETING_SINGLE_CALL_TOOL_NAMES,
    main_approval_tool_limit_middleware,
    meeting_tool_call_limit_middleware,
)
from .orchestration.graph import build_checkpointer
from .subagents.registry import build_subagents
from .orchestration.tool_registry import business_tools, main_tools, meeting_workflow_enabled


# OA 主图不是代码执行助手。DeepAgents 默认附带的文件系统、待办和通用子 Agent
# 会把较长的工具说明注入每一轮模型上下文，既不参与业务闭环，也会显著拉长小模型的
# 工具选路时间。这里仅从“模型可见工具”中移除它们：底层中间件仍保留，确保
# DeepAgents 的 task 分发基础设施不被破坏；业务领域 task 和全部领域子 Agent 不受影响。
_OA_HARNESS_EXCLUDED_TOOLS = frozenset({
    "write_todos", "ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute",
})


def _configure_oa_harness_profile() -> None:
    """注册 OA 专用的 DeepAgents 运行外壳，缩小无关上下文。

    参数：无。当前主图建图占位模型是 ``ChatOpenAI``，因此使用 ``openai``
    provider profile；真实模型仍由 ``DynamicModelMiddleware`` 在每个 Run
    按 Java 配置替换。该 profile 不改写领域提示词、不改变 WorkOrder、不改变
    工具执行权限，只收缩模型看到的默认控制面。
    """

    register_harness_profile(
        "openai",
        HarnessProfile(
            excluded_tools=_OA_HARNESS_EXCLUDED_TOOLS,
            # OA 只允许中央编译后委派明确的领域 Agent；默认 general-purpose
            # 子 Agent 没有业务契约，保留它只会扩大 task 描述和误委派空间。
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            tool_description_overrides={
                "task": """委派已编译的业务工作单给指定领域 Agent。只能使用中央计划投影签发的 task，不能自行补造 task 参数或改写工作单。\n\n可用领域 Agent：\n{available_agents}""",
            },
        ),
    )


# 本模块会在 LangGraph worker 进程启动时只导入一次。提前注册使主图和其声明式
# 子 Agent 使用同一份精简外壳；不在请求处理期间注册，避免跨 Run 累积配置。
_configure_oa_harness_profile()

def skill_files() -> dict[str, dict[str, str]]:
    """向 StateBackend 暴露 Skill 文件资源，但不在启动时全量加载到提示词中。"""
    return {
        path: create_file_data(content)
        for path, content in skill_registry.files().items()
    }


def build_agent(*, use_checkpointer: bool = True):
    """构建 OA Agent。

    控制台运行时使用项目配置的 checkpoint；LangGraph Server 运行时由
    LangGraph API 自己管理 persistence，因此不能再传入自定义 saver。
    """
    current_business_time = datetime.now(AGENT_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    # DeepAgents 建图时需要 BaseChatModel；真实模型由 DynamicModelMiddleware 在
    # 每个 Run 中从 Java 设置服务解析。此处不可路由的本地占位模型只为兼容建图，
    # 绝不能调用 OpenAI 网关或充当后备供应商。
    chat_model = ChatOpenAI(
        model="gpt-5.6-luna",
        api_key="runtime-model-is-resolved-per-run",
        base_url="http://127.0.0.1:9/v1",
        default_headers={"User-Agent": "kodagent-deepagents/0.1"},
        use_responses_api=False,
        streaming=True,
        max_retries=0,
        timeout=1,
    )

    # 领域子 Agent 规格统一由 subagent registry 维护。
    subagents = build_subagents(
        current_business_time,
        # 确定性工作流只是其覆盖契约的优先执行器，不替代完整会议领域。仍保留
        # ReAct 子 Agent 处理追问和工作流刻意未覆盖的复杂多步请求。
        include_meeting_agent=True,
    )

    all_tools = business_tools()
    apply_tool_contracts(all_tools)
    dynamic_model_middleware = DynamicModelMiddleware()
    main_phase_prompt_middleware = MainAgentPhasePromptMiddleware()

    return create_deep_agent(
        model=chat_model,
        tools=main_tools(),
        middleware=build_middleware_chain(
            dynamic_model=dynamic_model_middleware,
            phase_prompt=main_phase_prompt_middleware,
        ),
        interrupt_on={
            "confirm_meeting_booking": {
                "allowed_decisions": ["approve", "reject"],
                "description": confirmation_description,
                "when": prepare_confirmation_interrupt,
            },
            "confirm_personal_schedule": {
                "allowed_decisions": ["approve", "reject"],
                "description": personal_schedule_confirmation_description,
                "when": prepare_personal_schedule_confirmation,
            },
            "confirm_approval_batch_action": {
                "allowed_decisions": ["approve", "reject"],
                "description": approval_batch_confirmation_description,
                "when": prepare_approval_batch_confirmation,
            },
            "confirm_approval_task_action": {
                "allowed_decisions": ["approve", "reject"],
                "description": approval_task_confirmation_description,
                "when": prepare_approval_task_confirmation,
            },
            "confirm_approval_request_action": {
                "allowed_decisions": ["approve", "reject"],
                "description": approval_request_confirmation_description,
                "when": prepare_approval_request_confirmation,
            },
            "confirm_create_party_file": {
                "allowed_decisions": ["approve", "reject"],
                "description": "确认发布党务文件",
                "when": prepare_party_file_confirmation,
            },
            "confirm_update_party_file": {
                "allowed_decisions": ["approve", "reject"],
                "description": "确认更新党务文件",
                "when": prepare_party_file_confirmation,
            },
            "confirm_delete_party_file": {
                "allowed_decisions": ["approve", "reject"],
                "description": "确认删除党务文件",
                "when": prepare_party_file_confirmation,
            },
        },
        subagents=subagents,
        # The parent intentionally has no global Skill source.  The phase
        # middleware injects only the Skill selected after capability routing;
        # child agents declare their own domain source in the registry.
        system_prompt=MAIN_AGENT_COMMON_PROMPT,
        checkpointer=build_checkpointer() if use_checkpointer else None,
        name="oa-main-agent",
    )
