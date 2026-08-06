import json

from src.domain.errors import describe_error_code
from src.tools.common.contracts import tool_failure


def test_legacy_tool_error_keeps_code_and_exposes_recovery_metadata():
    response = tool_failure("MEETING_FACADE_UNAVAILABLE", "会议服务暂时不可用")
    payload = json.loads(response.to_tool_content())
    assert payload["error"]["code"] == "MEETING_FACADE_UNAVAILABLE"
    assert payload["error"]["kind"] == "dependency"
    assert payload["error"]["retryable"] is True


def test_error_code_classification_does_not_depend_on_user_message():
    descriptor = describe_error_code("PARTY_FILE_CATEGORY_REQUIRED")
    assert descriptor.kind == "validation"
    assert descriptor.retryable is False


def test_model_errors_keep_model_category_even_when_code_contains_invalid():
    assert describe_error_code("MODEL_REQUEST_INVALID").kind == "model"
    assert describe_error_code("MODEL_PROVIDER_UNAVAILABLE").retryable is True
