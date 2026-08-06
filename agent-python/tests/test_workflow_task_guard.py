from src.middleware.workflow_task_guard import _guard


def _state(text, call):
    return {"messages": [
        {"type": "human", "content": text},
        {"type": "ai", "tool_calls": [call]},
    ]}


def test_schedule_write_cannot_bypass_workflow_with_task(monkeypatch):
    monkeypatch.setattr(
        "src.middleware.workflow_task_guard.current_agent_context",
        lambda: {"runId": "run-1", "messageId": "msg-1"},
    )
    result = _guard(_state(
        "创建个人日程，明天 9 点到 10 点",
        {"name": "task", "id": "task-1", "args": {"subagent_type": "schedules_agent"}},
    ))
    assert result is not None
    assert "run_personal_schedule_workflow" in result["messages"][0].content


def test_read_only_schedule_query_can_still_delegate(monkeypatch):
    monkeypatch.setattr(
        "src.middleware.workflow_task_guard.current_agent_context",
        lambda: {"runId": "run-1", "messageId": "msg-1"},
    )
    result = _guard(_state(
        "查看明天的个人日程",
        {"name": "task", "id": "task-1", "args": {"subagent_type": "schedules_agent"}},
    ))
    assert result is None
