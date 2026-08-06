from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.oa_agent import (
    MainAgentPhasePromptMiddleware,
    classify_main_agent_phase,
    main_agent_phase_instructions,
    main_agent_prompt_for_phase,
)


def _task_call(name: str = "task"):
    return {"name": name, "args": {}, "id": "call-1", "type": "tool_call"}


def test_phase_classifier_uses_latest_turn_and_real_tool_results():
    assert classify_main_agent_phase([HumanMessage(content="查待办")]) == "planning"

    executing = [
        HumanMessage(content="查待办"),
        AIMessage(content="", tool_calls=[_task_call("route_conversation")]),
        ToolMessage(content="已识别为审批查询", name="route_conversation", tool_call_id="call-1"),
    ]
    assert classify_main_agent_phase(executing) == "executing"

    synthesizing = [
        HumanMessage(content="查待办"),
        AIMessage(content="", tool_calls=[_task_call()]),
        ToolMessage(content="完整审批列表", name="task", tool_call_id="call-1"),
    ]
    assert classify_main_agent_phase(synthesizing) == "synthesizing"

    unnamed_task_result = [
        HumanMessage(content="查文件"),
        AIMessage(content="", tool_calls=[_task_call()]),
        ToolMessage(content="完整文件列表", tool_call_id="call-1"),
    ]
    assert classify_main_agent_phase(unnamed_task_result) == "synthesizing"

    assert classify_main_agent_phase(synthesizing + [HumanMessage(content="再查日程")]) == "planning"

    pending_confirmation = [
        HumanMessage(content="预约会议室"),
        AIMessage(content="", tool_calls=[_task_call()]),
        ToolMessage(
            content='{"requires_confirmation":true,"confirmation_token":"draft-1"}',
            name="task",
            tool_call_id="call-1",
        ),
    ]
    assert classify_main_agent_phase(pending_confirmation) == "executing"


def test_phase_prompts_have_separate_responsibilities():
    planning = main_agent_phase_instructions("planning")
    executing = main_agent_phase_instructions("executing")
    synthesis = main_agent_phase_instructions("synthesizing")

    assert "选择正确的执行路径" in planning
    assert "核对工具返回的真实数据" in executing
    assert "最终用户答复" in synthesis
    assert "最终用户答复" not in planning
    assert "route_conversation" not in synthesis
    assert "不能把子 Agent 的 output 原样逐字复制" in synthesis
    assert "当前业务时间" in main_agent_prompt_for_phase("planning")


def test_main_phase_middleware_overrides_only_parent_request_prompt():
    request = SimpleNamespace(
        state={
            "messages": [
                HumanMessage(content="查待办"),
                AIMessage(content="", tool_calls=[_task_call()]),
                ToolMessage(content="完整审批列表", name="task", tool_call_id="call-1"),
            ]
        },
        system_message=SystemMessage(content="公共安全约束"),
    )

    captured = {}

    def override(**kwargs):
        captured.update(kwargs)
        return kwargs["system_message"]

    request.override = override
    result = MainAgentPhasePromptMiddleware().wrap_model_call(request, lambda updated: updated)

    assert isinstance(result, SystemMessage)
    assert "<!-- kodagent-main-agent-phase:synthesizing -->" in result.content
    assert "当前阶段：最终总结（synthesizing）" in result.content
    assert "公共安全约束" in result.content
    assert "当前阶段：规划（planning）" not in result.content
