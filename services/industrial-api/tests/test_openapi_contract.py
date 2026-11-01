"""契约一致性：工业服务 OpenAPI 产物必须与当前应用一致。"""

import json
from pathlib import Path

from app.main import create_app

CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "industrial-api.openapi.json"


def test_openapi_contract_is_in_sync():
    current = create_app().openapi()
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert committed["openapi"] == current["openapi"], "OpenAPI 版本不一致"
    assert set(committed["paths"]) == set(current["paths"]), (
        "契约路径与实现不一致，请运行 services/industrial-api/scripts/export_openapi.py 重新导出\n"
        f"仅契约存在: {sorted(set(committed['paths']) - set(current['paths']))}\n"
        f"仅实现存在: {sorted(set(current['paths']) - set(committed['paths']))}"
    )


def test_contract_contains_critical_endpoints():
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for path in (
        "/api/v1/devices/{device_id}",
        "/api/v1/devices/{device_id}/faults",
        "/api/v1/devices/{device_id}/tickets",
        "/api/v1/tickets/precheck",
        "/api/v1/tickets",
        "/api/v1/tickets/{ticket_id}/status",
        "/api/v1/tickets/{ticket_id}/actions",
        "/api/v1/admin/customers",
        "/api/v1/admin/identity-bindings",
        "/api/v1/health",
    ):
        assert path in committed["paths"], path