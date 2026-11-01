"""故障注入驱动（ACC-06/ACC-12 故障演练）。

用法：
    python scripts/fault_drill.py --expect failed      # 工业服务停机时：必须 FAILED/TIMED_OUT
    python scripts/fault_drill.py --expect confirmed   # 恢复后：应回到 WAITING_CONFIRMATION/SUCCEEDED
"""

import argparse
import json
import os
import sys

import httpx

BASE = os.environ.get("FAULT_BASE", "http://127.0.0.1:8090")
PASSWORD = os.environ.get("FAULT_PASSWORD", "Passw0rd!2026")

EXPECTATIONS = {
    "failed": {"FAILED", "TIMED_OUT"},
    "confirmed": {"WAITING_CONFIRMATION", "SUCCEEDED"},
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", choices=sorted(EXPECTATIONS), default="failed")
    args = parser.parse_args()

    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        login = client.post("/api/flowai/auth/login", json={"username": "admin", "password": PASSWORD})
        login.raise_for_status()
        headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}

        session = client.post("/api/flowai/apps/service-agent/sessions", headers=headers)
        session.raise_for_status()
        conversation_id = session.json()["data"]["conversation_id"]

        response = client.post(
            f"/api/flowai/sessions/{conversation_id}/messages",
            json={"content": "device_id: 1 HC200 通信异常，请帮我创建工单"},
            headers=headers,
        )
        data = response.json().get("data", {})
        status = data.get("status")
        print(json.dumps({"http": response.status_code, "status": status}, ensure_ascii=False))

        expected = EXPECTATIONS[args.expect]
        if status not in expected:
            print(f"UNEXPECTED_STATUS status={status} expected={sorted(expected)}")
            return 2
        print(f"EXPECTATION_OK expect={args.expect} status={status}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())