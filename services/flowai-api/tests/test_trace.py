"""Trace ID 传播：入站沿用、缺失生成、响应头回写。"""

import re


def test_incoming_trace_id_is_echoed(client):
    response = client.get("/health", headers={"X-Trace-ID": "trace-abc-123"})
    assert response.headers["X-Trace-ID"] == "trace-abc-123"


def test_generated_trace_id_is_returned_when_missing(client):
    response = client.get("/health")
    trace_id = response.headers["X-Trace-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", trace_id)


def test_envelope_trace_id_matches_header(client):
    response = client.get("/api/v1/meta", headers={"X-Trace-ID": "trace-envelope-1"})
    assert response.json()["trace_id"] == "trace-envelope-1"
    assert response.headers["X-Trace-ID"] == "trace-envelope-1"


def test_blank_trace_header_is_regenerated(client):
    response = client.get("/health", headers={"X-Trace-ID": "   "})
    assert response.headers["X-Trace-ID"] != "   "
    assert len(response.headers["X-Trace-ID"]) == 32