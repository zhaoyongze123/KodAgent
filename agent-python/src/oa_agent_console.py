import os
import json
import sys
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from langgraph.types import Command

# PyCharm 有时会直接执行这个文件的绝对路径；此时没有 package context，
# 相对导入会失败。兼容“运行模块”和“直接运行文件”两种方式。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.oa_agent import build_agent, skill_files
    from src.tools.common.events import build_event, format_event_text, set_event_context
    from src.tools.common.http_client import persist_agent_event
else:
    from .oa_agent import build_agent, skill_files
    from .tools.common.events import build_event, format_event_text, set_event_context
    from .tools.common.http_client import persist_agent_event


console = Console()
_CONSOLE_CONVERSATION_ID: str | None = None


def _message_text(message_chunk: Any) -> str:
    content = getattr(message_chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


TOOL_LABELS = {
    "search_party_files": "党务文件查询",
    "get_party_file_detail": "党务文件详情",
    "get_party_file_attachment": "党务文件附件",
    "list_party_file_categories": "党务文件分类",
    "list_my_pending_approvals": "待办审批",
    "list_available_meeting_rooms": "会议室查询",
    "get_my_calendar": "个人日程",
    "get_current_meeting_user": "当前用户身份",
}

SUBAGENT_LABELS = {
    "approvals_agent": "审批助手",
    "meeting_rooms_agent": "会议室助手",
    "schedules_agent": "日程助手",
    "party_files_agent": "党务文件助手",
}

PROGRESS_ICONS = {
    "plan": "🧠",
    "agent_message": "🧩",
    "draft": "📝",
    "confirmation_required": "⚠️",
}


def _tool_name(message_chunk: Any) -> str:
    """从工具调用分片中提取工具名；名称可能只在其中一个分片出现。"""
    direct_name = getattr(message_chunk, "name", None)
    if direct_name:
        return direct_name
    for item in getattr(message_chunk, "tool_call_chunks", None) or []:
        if isinstance(item, dict) and item.get("name"):
            return item["name"]
    return "unknown_tool"


def _subagent_name(message_chunk: Any, task_args: dict[str, str]) -> str | None:
    """从完整或流式 task 参数中提取目标子 Agent 名称。"""
    for call in getattr(message_chunk, "tool_calls", None) or []:
        if call.get("name") != "task":
            continue
        args = call.get("args") or {}
        if isinstance(args, dict):
            return args.get("subagent_type") or args.get("name") or args.get("agent")

    for item in getattr(message_chunk, "tool_call_chunks", None) or []:
        if not isinstance(item, dict):
            continue
        if item.get("name") != "task" and item.get("id") not in task_args:
            continue
        call_id = item.get("id") or "task"
        args_fragment = item.get("args") or ""
        task_args[call_id] = task_args.get(call_id, "") + (
            json.dumps(args_fragment) if isinstance(args_fragment, dict) else str(args_fragment)
        )
        try:
            args = json.loads(task_args[call_id])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(args, dict):
            return args.get("subagent_type") or args.get("name") or args.get("agent")
    return None


def stream_answer(agent: Any, user_message: str) -> str:
    answer = ""
    started_at = perf_counter()
    tenant_id = os.getenv("OA_AGENT_TENANT_ID", "1")
    user_id = os.getenv("OA_AGENT_USER_ID", "1")
    global _CONSOLE_CONVERSATION_ID
    if _CONSOLE_CONVERSATION_ID is None:
        _CONSOLE_CONVERSATION_ID = os.getenv("OA_AGENT_CONVERSATION_ID") or str(uuid.uuid4())
    conversation_id = _CONSOLE_CONVERSATION_ID
    thread_id = f"oa:{tenant_id}:{user_id}:{conversation_id}"
    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    set_event_context(run_id, thread_id, tenant_id, user_id, conversation_id, message_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {"runId": run_id, "tenantId": tenant_id, "userId": user_id,
                     "conversationId": conversation_id, "messageId": message_id},
        "tags": ["kodagent", "console"],
    }
    answer_started = False
    printed_statuses: set[str] = set()
    task_args: dict[str, str] = {}

    def print_status(text: str) -> None:
        nonlocal answer_started
        if text in printed_statuses:
            return
        if answer_started:
            console.print()
            answer_started = False
        console.print(f"[cyan]{text}[/cyan]")
        printed_statuses.add(text)

    def lifecycle(event_type: str, **data: Any) -> None:
        try:
            persist_agent_event(build_event(event_type, data))
        except Exception:
            pass

    lifecycle("run.created", userMessage=user_message[:300])
    print_status("🧠 正在理解你的问题……")
    input_data: Any = {
        "messages": [{"role": "user", "content": user_message}],
        "files": skill_files(),
    }
    while True:
      interrupted = False
      for chunk in agent.stream(input_data, config=config, stream_mode=["messages", "custom"], subgraphs=True, version="v2"):
        mode = chunk["type"]
        payload = chunk["data"]
        if mode in {"interrupt", "__interrupt__"} or (isinstance(payload, dict) and "__interrupt__" in payload):
            interrupted = True
            lifecycle("run.paused", reason="approval_required")
            print_status("⚠️ 预约草稿已生成，请输入“确认”提交，或输入“取消”放弃：")
            decision = console.input("[bold yellow]确认/取消：[/bold yellow]").strip().lower()
            input_data = Command(resume={"decisions": [{"type": "approve" if decision in {"确认", "confirm", "yes", "y"} else "reject"}]})
            lifecycle("run.resumed", decision="approve" if decision in {"确认", "confirm", "yes", "y"} else "reject")
            break
        if mode == "custom":
            event = payload.get("event") if isinstance(payload, dict) else None
            if event:
                event_type = event.get("type")
                data = event.get("data", {})
                text = format_event_text(event)
                if text: print_status(text)
            elif isinstance(payload, dict) and payload.get("text"):
                stage = payload.get("stage")
                text = payload["text"]
                if stage in PROGRESS_ICONS and not text.startswith(tuple(PROGRESS_ICONS.values())):
                    text = f"{PROGRESS_ICONS[stage]} {text}"
                print_status(text)
            continue

        message_chunk = payload[0] if isinstance(payload, tuple) else payload
        message_type = getattr(message_chunk, "type", "")

        # subgraphs=True 会同时返回子 Agent 和主 Agent 的消息。
        # 子 Agent 的业务状态仍通过 custom 事件展示，但它的中间回答不直接打印，
        # 否则会出现“子 Agent 回答一次、主 Agent 汇总后又回答一次”。
        is_subgraph_message = bool(chunk.get("ns"))
        if message_type == "tool":
            # 业务 Tool 会通过 custom 事件主动报告完成状态；不再额外打印
            # report_progress/task 的通用 ToolMessage，避免出现重复状态。
            continue
        if getattr(message_chunk, "tool_call_chunks", None) or getattr(message_chunk, "tool_calls", None):
            # 子 Agent 的 Tool 自己会通过 custom 事件发送更准确的状态，
            # 不再额外显示笼统的“业务工具”提示。
            if not is_subgraph_message:
                tool_name = _tool_name(message_chunk)
                if tool_name == "task":
                    subagent_name = _subagent_name(message_chunk, task_args)
                    if subagent_name:
                        tool_label = SUBAGENT_LABELS.get(subagent_name, subagent_name)
                        print_status(f"🧩 正在调用「{tool_label}」……")
                elif tool_name not in {"unknown_tool", "report_progress"}:
                    tool_label = TOOL_LABELS.get(tool_name, tool_name)
                    print_status(f"🔧 正在调用「{tool_label}」工具……")
            continue

        if is_subgraph_message:
            continue

        content = _message_text(message_chunk)
        if content and message_type in {"ai", "AIMessageChunk"}:
            if not answer_started:
                print_status("✍️ 正在生成回答……")
                answer_started = True
            answer += content
            sys.stdout.write(content)
            sys.stdout.flush()

      if not interrupted:
        break
    if answer_started:
        console.print()
    console.print(f"[dim]✅ 完成 · {perf_counter() - started_at:.1f}s[/dim]")
    lifecycle("run.completed", durationMs=int((perf_counter() - started_at) * 1000))
    return answer


def run_chat(agent: Any) -> None:
    console.print(
        Panel(
            "OA 助手已启动\n"
            "支持审批、会议室、日历和党务文件查询。\n"
            "输入 exit 或 退出结束。",
            title="KodAgent",
            border_style="green",
        )
    )
    while True:
        try:
            user_message = console.input("[bold cyan]你：[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已退出。[/yellow]")
            return
        if not user_message:
            continue
        if user_message.lower() in {"exit", "quit", "退出"}:
            console.print("[yellow]已退出。[/yellow]")
            return
        stream_answer(agent, user_message)


def main() -> None:
    # 无论 PyCharm 的 Working directory 如何设置，都读取 agent-python/.env。
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    run_chat(build_agent())


if __name__ == "__main__":
    main()
