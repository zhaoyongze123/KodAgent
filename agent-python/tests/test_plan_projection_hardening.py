from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from src.orchestration.plan_projection import PlanToolProjectionMiddleware


class _Request(SimpleNamespace):
    def override(self, **changes):
        values = dict(self.__dict__)
        values.update(changes)
        return _Request(**values)


def test_synthesis_never_reexposes_confirmation_tool(monkeypatch):
    """A stale WAITING_APPROVAL task cannot grant a later model a write tool."""
    tools = [
        SimpleNamespace(name="confirm_meeting_booking"),
        SimpleNamespace(name="route_conversation"),
    ]
    request = _Request(
        tools=tools,
        state={"messages": [
            ToolMessage(
                name="route_conversation",
                tool_call_id="route-call",
                content='{"data":{"planStatus":"RESOLVED","executionTool":"run_meeting_booking_workflow"}}',
            ),
            ToolMessage(name="run_meeting_booking_workflow", tool_call_id="workflow-call", content='{"ok":true}'),
            AIMessage(content="草稿已生成"),
        ]},
    )
    monkeypatch.setattr(
        "src.orchestration.plan_projection.classify_main_agent_phase",
        lambda _messages: "synthesizing",
    )

    updated = PlanToolProjectionMiddleware._override(request)

    assert updated.tools == []
