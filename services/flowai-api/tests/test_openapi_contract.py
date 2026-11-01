"""契约一致性：仓库中的 OpenAPI 产物必须与当前应用一致。"""

import json
from pathlib import Path

from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "flowai-api.openapi.json"


def test_openapi_contract_is_in_sync():
    app = create_app()
    current = app.openapi()
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert committed["openapi"] == current["openapi"], "OpenAPI 版本不一致"
    assert set(committed["paths"]) == set(current["paths"]), (
        "契约路径与实现不一致，请运行 services/flowai-api/scripts/export_openapi.py 重新导出\n"
        f"仅契约存在: {sorted(set(committed['paths']) - set(current['paths']))}\n"
        f"仅实现存在: {sorted(set(current['paths']) - set(committed['paths']))}"
    )


def test_contract_contains_critical_endpoints():
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for path in (
        "/api/v1/auth/login",
        "/api/v1/applications",
        "/api/v1/applications/{app_id}/publish",
        "/api/v1/knowledge-bases",
        "/api/v1/sessions/{conversation_id}/messages",
        "/api/v1/executions/{execution_id}/confirm",
        "/api/v1/monitoring/metrics",
    ):
        assert path in committed["paths"], path