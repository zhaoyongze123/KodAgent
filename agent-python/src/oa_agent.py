import os
from datetime import datetime
from pathlib import Path

from deepagents.backends.utils import create_file_data
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from .tools.common import (
    AGENT_TIMEZONE,
    apply_tool_contracts,
)
from .llm.runtime import DynamicModelMiddleware, RunLifecycleMiddleware
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

SKILL_FILE = Path(__file__).resolve().parents[1] / "skills/meeting-room-booking/SKILL.md"

def skill_files() -> dict[str, dict[str, str]]:
    """为默认 StateBackend 提供项目 Skill 文件。"""
    return {
        "/skills/meeting-room-booking/SKILL.md": create_file_data(
            SKILL_FILE.read_text(encoding="utf-8")
        ),
    }


def build_agent(*, use_checkpointer: bool = True):
    """构建 OA Agent。

    控制台运行时使用项目配置的 checkpoint；LangGraph Server 运行时由
    LangGraph API 自己管理 persistence，因此不能再传入自定义 saver。
    """
    current_business_time = datetime.now(AGENT_TIMEZONE).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    # DeepAgents needs a BaseChatModel while assembling the graph, but the
    # real model is resolved per Run by DynamicModelMiddleware from the Java
    # settings service.  This local, non-routable placeholder retains the
    # historical construction name for compatibility, but can never call an
    # OpenAI gateway or act as a fallback provider.
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

    # Domain child specifications are owned by the subagent registry.
    subagents = build_subagents(
        current_business_time,
        # A deterministic workflow is the preferred executor for its covered
        # contract, not a replacement for the whole meeting domain.  Keep the
        # ReAct child registered for follow-up questions and unsupported
        # multi-step requests that the workflow intentionally does not model.
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
        skills=["/skills/"],
        # The parent starts with the compact common prompt. The phase
        # middleware replaces it for each model call, so child agents keep
        # their own domain prompts and are never affected by parent phases.
        system_prompt=MAIN_AGENT_COMMON_PROMPT,
        checkpointer=build_checkpointer() if use_checkpointer else None,
        name="oa-main-agent",
    )
