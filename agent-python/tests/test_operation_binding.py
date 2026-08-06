from datetime import datetime, timezone

import pytest

from src.domain.operation_binding import OperationBinding, OperationDraftEnvelope


def test_operation_binding_is_domain_neutral_and_strict():
    binding = OperationBinding(
        operation_id="draft-1", domain="meeting", operation="UPDATE", status="PENDING",
        tenant_id="1", user_id="2", run_id="run-1", thread_id="thread-1",
        message_id="message-1", idempotency_key="idem-1", expires_at=datetime.now(timezone.utc),
    )
    envelope = OperationDraftEnvelope(binding=binding, payload={"sourceBookingId": 10}, card_type="meeting_booking")
    assert envelope.binding.operation == "UPDATE"
    with pytest.raises(ValueError):
        OperationBinding(
            operation_id="", domain="meeting", operation="CREATE", status="PENDING",
            tenant_id="1", user_id="2", run_id="run", thread_id="thread", message_id="message", idempotency_key="id",
        )
