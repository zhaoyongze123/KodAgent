from src.tools import reports


def test_report_rejects_invalid_range():
    result = reports.meeting_report.func("2026-08-03 14:00:00", "2026-08-03 12:00:00")
    assert result.error.code == "REPORT_RANGE_INVALID"


def test_report_uses_backend_aggregation_and_card(monkeypatch):
    monkeypatch.setattr(reports, "get_stream_writer", lambda: None)
    monkeypatch.setattr(reports, "java_get", lambda path, params: {"reportType": "meeting", "total": 2, "byRoom": {"A101": 2}})
    result = reports.meeting_report.func("2026-08-03 12:00:00", "2026-08-03 14:00:00")
    assert result.ok is True
    assert result.data["total"] == 2
    assert result.presentation["cardType"] == "business_report"
