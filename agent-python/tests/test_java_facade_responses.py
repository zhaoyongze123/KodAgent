import httpx
import pytest
from types import SimpleNamespace

from src.tools.common import http_client
from src.tools.meeting import conflicts


@pytest.mark.parametrize(
    ("method", "path", "tool_name"),
    [
        ("GET", "/agent/tools/meetings/rooms", "list_available_meeting_rooms"),
        ("GET", "/agent/tools/meetings/my", "list_my_meeting_bookings"),
        ("GET", "/agent/tools/meetings/report", "meeting_report"),
        ("POST", "/agent/tools/meetings/conflict-check", "check_meeting_room_conflict"),
        ("POST", "/agent/tools/meetings/book", "confirm_meeting_booking"),
        ("GET", "/agent/tools/meetings/40", "get_my_meeting_booking"),
        ("GET", "/agent/tools/users/search", "search_meeting_attendees"),
        ("GET", "/agent/tools/users/me", "get_current_meeting_user"),
        ("POST", "/agent/tools/calendar/users", "get_meeting_attendees_calendar"),
        ("GET", "/agent/tools/calendar/my", "get_my_calendar"),
        ("GET", "/agent/tools/calendar/report", "schedule_report"),
        ("GET", "/agent/tools/approvals/types", "list_startable_approval_types"),
        ("GET", "/agent/tools/approvals/inbox", "search_my_pending_approvals"),
        ("GET", "/agent/tools/party-knowledge/search", "search_party_knowledge"),
        ("POST", "/agent/tools/party-knowledge/search", "search_party_knowledge"),
        ("GET", "/agent/tools/party-knowledge/health", "check_party_knowledge_health"),
        ("GET", "/agent/tools/approvals/insights", "analyze_my_pending_approvals"),
        ("POST", "/agent/tools/approvals/preview", "preview_approval_request"),
        ("POST", "/agent/tools/approvals/request-draft", "create_approval_request_draft"),
        ("POST", "/agent/tools/approvals/request-commit", "confirm_approval_request_action"),
        ("POST", "/agent/tools/approvals/generic/draft", "create_generic_approval_request_draft"),
        ("POST", "/agent/tools/approvals/generic/commit", "confirm_approval_request_action"),
        ("POST", "/agent/tools/approvals/withdraw-draft", "create_approval_withdraw_draft"),
        ("POST", "/agent/tools/approvals/withdraw-commit", "confirm_approval_withdraw_action"),
        ("POST", "/agent/tools/approvals/batch/preview", "preview_approval_batch_action"),
        ("POST", "/agent/tools/approvals/batch/execute", "confirm_approval_batch_action"),
        ("POST", "/agent/tools/approvals/batch/preview-1/reconcile", "reconcile_approval_batch_action"),
        ("GET", "/agent/tools/tasks/todo", "list_my_pending_approvals"),
        ("POST", "/agent/tools/tasks/action-preview", "preview_approval_task_action"),
        ("POST", "/agent/tools/tasks/action-execute", "confirm_approval_task_action"),
        ("POST", "/agent/tools/tasks/action-reconcile", "reconcile_approval_task_action"),
        ("POST", "/agent/tools/party-files/query-plan", "execute_party_file_metadata_plan"),
        ("GET", "/agent/tools/party-files/report", "party_file_report"),
        ("GET", "/agent/tools/party-files/my-page", "search_party_files"),
        ("GET", "/agent/tools/party-files/my-get", "get_party_file_detail"),
        ("GET", "/agent/tools/party-files/my-attachment", "get_party_file_attachment"),
        ("GET", "/agent/tools/party-files/categories", "list_party_file_categories"),
        ("POST", "/agent/drafts/meeting-booking", "create_meeting_booking_draft"),
        ("GET", "/agent/config/resolve", "resolve_agent_model"),
        ("GET", "/agent/tools/approvals/batch/preview-1", "preview_approval_batch_action"),
        ("POST", "/agent/tools/approvals/batch/preview-1/approve", "confirm_approval_batch_action"),
        ("GET", "/agent/tools/tasks/task-1", "get_approval_task_detail"),
        ("GET", "/agent/tools/calendar/personal-schedules/drafts/draft-1", "get_personal_schedule_draft"),
        ("GET", "/agent/tools/calendar/personal-schedules/123", "get_personal_schedule"),
        ("POST", "/agent/tools/calendar/personal-schedules/drafts", "create_personal_schedule_draft"),
        ("POST", "/agent/tools/calendar/personal-schedules/commit", "confirm_personal_schedule"),
        ("GET", "/agent/tools/party-knowledge/documents/10", "get_party_knowledge_document"),
        ("GET", "/agent/tools/party-knowledge/chunks/20", "get_party_knowledge_chunk"),
        ("GET", "/agent/drafts/meeting-booking/draft-1", "get_meeting_booking_draft"),
        ("POST", "/agent/drafts/meeting-booking/draft-1/status", "update_meeting_booking_draft_status"),
        ("DELETE", "/agent/drafts/meeting-booking/draft-1", "delete_meeting_booking_draft"),
        ("POST", "/agent/runs/run-1/events", "agent_event_persist"),
        ("GET", "/agent/runs/run-1/events", "get_agent_run_events"),
        ("POST", "/agent/runs/run-1/cancel", "cancel_agent_run"),
        ("POST", "/agent/runs/run-1/metrics", "record_agent_run_metric"),
        ("GET", "/agent/threads/thread-1/events", "get_agent_thread_events"),
        ("GET", "/agent/approvals/approval-1/pending-card", "get_meeting_booking_approval"),
        ("GET", "/agent/approvals/pending-card/by-draft/draft-1", "get_meeting_booking_approval"),
        ("POST", "/agent/approvals/approval-1/resume", "decide_agent_approval"),
        ("GET", "/agent/config/models", "list_agent_models"),
    ],
)
def test_facade_route_contract_covers_static_and_dynamic_paths(method, path, tool_name):
    assert http_client._tool_name_for_path(path, method) == tool_name


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/agent/tools/calendar/personal-schedules/drafts/draft-1/status"),
        ("DELETE", "/agent/drafts/meeting-booking/draft-1/status"),
        ("GET", "/agent/runs/run-1/cancel"),
        ("POST", "/agent/runs/run-1/events/extra"),
        ("POST", "/agent/approvals/approval-1/unknown"),
        ("GET", "/agent/tools/meetings/40/extra"),
        ("GET", "/agent/tools/meetings/not-a-number"),
        ("GET", "/agent/tools/party-knowledge/documents/not-a-number"),
        ("POST", "/agent/tools/meetings/40"),
        ("POST", "/agent/tools/approvals/batch/preview-1/unknown"),
        ("GET", "/agent/tools/approvals"),
    ],
)
def test_facade_route_contract_rejects_unknown_dynamic_shapes(method, path):
    with pytest.raises(RuntimeError, match="未登记 Java Facade 路径"):
        http_client._tool_name_for_path(path, method)


def response(status_code: int, content: bytes, content_type: str = "application/json") -> httpx.Response:
    return httpx.Response(
        status_code,
        content=content,
        headers={"content-type": content_type},
        request=httpx.Request("POST", "http://java.test/agent/tools/calendar/users"),
    )


def test_decode_json_allows_top_level_list_response():
    result = http_client._decode_json_or_empty(
        response(200, b'[{"userId":1,"events":[]}]'),
        path="/agent/tools/calendar/users",
        expected_type="list",
    )

    assert result == [{"userId": 1, "events": []}]


def test_decode_json_preserves_empty_204_response_as_object():
    assert http_client._decode_json_or_empty(response(204, b"")) == {}


def test_default_object_contract_rejects_top_level_list():
    with pytest.raises(http_client.JavaFacadeResponseTypeError) as raised:
        http_client._decode_json_or_empty(
            response(200, b'[{"userId":1}]'), path="/agent/tools/users/me"
        )

    assert raised.value.path == "/agent/tools/users/me"
    assert raised.value.expected_type == "object"
    assert raised.value.actual_type == "list"


def test_list_contract_accepts_top_level_list(monkeypatch):
    monkeypatch.setattr(
        http_client,
        "_request",
        lambda *args, **kwargs: response(200, b'[{"userId":1}]'),
    )

    assert http_client.java_post_list("/agent/tools/calendar/users", {"userIds": [1]}) == [
        {"userId": 1}
    ]


def test_decode_json_distinguishes_business_error_envelope():
    with pytest.raises(http_client.JavaFacadeBusinessError) as raised:
        http_client._decode_json_or_empty(
            response(200, '{"code":500,"msg":"日历查询失败"}'.encode()),
            path="/agent/tools/calendar/users",
        )

    assert raised.value.code == 500
    assert raised.value.message == "日历查询失败"


def test_decode_json_distinguishes_invalid_json():
    with pytest.raises(http_client.JavaFacadeJsonDecodeError) as raised:
        http_client._decode_json_or_empty(
            response(200, b"not-json", "text/plain"), path="/agent/tools/calendar/users"
        )

    assert raised.value.status_code == 200
    assert raised.value.content_type == "text/plain"


def test_decode_json_rejects_scalar_response_type():
    with pytest.raises(http_client.JavaFacadeResponseTypeError) as raised:
        http_client._decode_json_or_empty(
            response(200, b"true"), path="/agent/tools/users/me"
        )

    assert raised.value.actual_type == "bool"


def test_request_distinguishes_http_failure(monkeypatch):
    monkeypatch.setenv("OA_AGENT_CONSOLE_DEV_MODE", "true")
    class FakeClient:
        def request(self, *args, **kwargs):
            return response(503, b'{"message":"temporarily unavailable"}')

    monkeypatch.setattr(
        http_client,
        "_get_shared_http_client",
        lambda: FakeClient(),
    )

    with pytest.raises(http_client.JavaFacadeHttpError) as raised:
        http_client._request("GET", "/agent/tools/users/me")

    assert raised.value.status_code == 503


def test_request_distinguishes_connection_failure(monkeypatch):
    monkeypatch.setenv("OA_AGENT_CONSOLE_DEV_MODE", "true")

    class FakeClient:
        def request(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(http_client, "_get_shared_http_client", lambda: FakeClient())

    with pytest.raises(http_client.JavaFacadeConnectionError):
        http_client._request("GET", "/agent/tools/users/me")


def test_shared_http_client_is_reused_within_one_process(monkeypatch):
    created = []

    class FakeClient:
        def close(self):
            return None

    def factory():
        client = FakeClient()
        created.append(client)
        return client

    http_client._close_shared_http_client()
    monkeypatch.setattr(http_client, "_new_http_client", factory)
    first = http_client._get_shared_http_client()
    second = http_client._get_shared_http_client()
    try:
        assert first is second
        assert len(created) == 1
    finally:
        http_client._close_shared_http_client()


def test_retryable_read_statuses_follow_contract(monkeypatch):
    responses = iter([
        response(500, b'{"message":"temporary"}'),
        response(200, b'{"items":[]}'),
    ])
    calls = []

    class FakeClient:
        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return next(responses)

    monkeypatch.setenv("OA_AGENT_CONSOLE_DEV_MODE", "true")
    monkeypatch.setattr(http_client, "_get_shared_http_client", lambda: FakeClient())
    result = http_client._request("GET", "/agent/tools/meetings/my")

    assert result.status_code == 200
    assert len(calls) == 2


def test_batch_calendar_list_continues_to_room_conflict_check(monkeypatch):
    calls = []
    responses = iter([
        [{"userId": 1, "userNickname": "张三", "events": []}],
        {"conflicts": []},
    ])

    monkeypatch.setattr(conflicts, "meeting_request_gate", lambda **kwargs: None)
    monkeypatch.setattr(conflicts, "get_stream_writer", lambda: None)
    monkeypatch.setattr(conflicts, "save_availability_check", lambda check: "availability-1")
    monkeypatch.setattr(conflicts, "current_agent_context", lambda: {"messageId": "m-1", "runId": "r-1"})
    monkeypatch.setattr(
        conflicts,
        "merge_operation_payload",
        lambda patch: SimpleNamespace(operation_id="op-meeting-test"),
    )

    def java_post_list(path, payload):
        calls.append(path)
        return next(responses)

    monkeypatch.setattr(conflicts, "java_post_list", java_post_list)
    monkeypatch.setattr(conflicts, "java_post", java_post_list)

    result = conflicts.check_meeting_availability_batch.func(
        meeting_rooms=[{"id": 101, "name": "A101", "capacity": 10}],
        user_ids=[1],
        start_time="2026-07-29 13:00:00",
        end_time="2026-07-29 15:00:00",
    )

    assert result.ok is True
    assert calls == [
        "/agent/tools/calendar/users",
        "/agent/tools/meetings/conflict-check",
    ]
    assert result.data["recommended"]["meetingRoomId"] == 101


def test_single_room_conflict_does_not_hide_invalid_json_as_unavailable(monkeypatch):
    monkeypatch.setattr(conflicts, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        conflicts,
        "java_post",
        lambda path, payload: (_ for _ in ()).throw(
            http_client.JavaFacadeJsonDecodeError(200, "text/plain", path)
        ),
    )

    result = conflicts.check_meeting_room_conflict.func(
        meeting_room_id=101,
        start_time="2026-07-29 13:00:00",
        end_time="2026-07-29 15:00:00",
    )

    assert result.ok is False
    assert result.error.code == "MEETING_FACADE_INVALID_JSON"
