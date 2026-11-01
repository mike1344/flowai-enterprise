"""日志安全：结构化 JSON、访问日志不含凭证、脱敏工具生效。"""

import json
import logging

from app.core.logging import JsonFormatter
from app.core.redaction import REDACTED, redact_headers, redact_mapping


def test_json_formatter_emits_single_line_json():
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace-1"
    record.status = 200
    line = JsonFormatter().format(record)
    assert "\n" not in line
    payload = json.loads(line)
    assert payload["message"] == "hello"
    assert payload["trace_id"] == "trace-1"
    assert payload["status"] == 200


def test_access_log_does_not_leak_credentials(client, caplog):
    with caplog.at_level(logging.INFO):
        client.get(
            "/api/v1/meta",
            headers={
                "Authorization": "Bearer SUPER-SECRET-TOKEN",
                "Cookie": "flowai_session=session-secret",
                "X-CSRF-Token": "csrf-secret",
            },
        )

    logged = " ".join(record.getMessage() for record in caplog.records)
    logged += " ".join(str(record.__dict__.get("args", "")) for record in caplog.records)
    logged += " ".join(
        json.dumps(record.__dict__, default=str, ensure_ascii=False) for record in caplog.records
    )
    for secret in ("SUPER-SECRET-TOKEN", "session-secret", "csrf-secret"):
        assert secret not in logged


def test_redact_headers_masks_credentials():
    headers = redact_headers(
        {"Authorization": "Bearer abc", "Cookie": "sid=1", "Accept": "application/json"}
    )
    assert headers["Authorization"] == REDACTED
    assert headers["Cookie"] == REDACTED
    assert headers["Accept"] == "application/json"


def test_redact_mapping_handles_nested_keys():
    payload = {
        "user": {"name": "张三", "api_key": "sk-live-123"},
        "database_url": "mysql://u:p@h/db",
        "items": [{"token": "t-1", "title": "ok"}],
    }
    redacted = redact_mapping(payload)
    assert redacted["user"]["api_key"] == REDACTED
    assert redacted["user"]["name"] == "张三"
    assert redacted["items"][0]["token"] == REDACTED
    assert redacted["items"][0]["title"] == "ok"