"""ACC-04 Agent 任务集：20 个任务，正常路径成功率 ≥95%，异常路径必须安全失败。

任务构成：
  - 12 个只读任务（设备信息 / 故障 / 工单，不同表述）→ 期望 SUCCEEDED 且回答含设备编号
  - 4 个写意图任务 → 期望 WAITING_CONFIRMATION（未确认不写），随后 reject 取消
  - 2 个模糊/无设备任务 → 期望 SUCCEEDED（提示无法识别设备），不得写入
  - 2 个不存在设备任务 → 期望 FAILED/SUCCEEDED 但不得创建工单

用法：python scripts/agent_task_suite.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("AGENT_BASE", "http://127.0.0.1:8090")
PASSWORD = os.environ.get("AGENT_PASSWORD", "Passw0rd!2026")
SLUG = os.environ.get("AGENT_SLUG", "service-agent")

READ_TASKS = [
    ("device_id: 1 这台设备有什么故障历史？", "1"),
    ("device_id: 2 报过什么故障", "2"),
    ("device_id: 3 的工单情况", "3"),
    ("device_id: 1 现在状态如何", "1"),
    ("帮我查一下 device_id: 2 的设备信息", "2"),
    ("device_id: 3 有没有未关闭工单", "3"),
    ("device_id: 1 的型号和保修信息", "1"),
    ("device_id: 2 最近一次故障是什么", "2"),
    ("device_id: 3 的客户是谁", "3"),
    ("device_id: 1 有哪些历史工单", "1"),
    ("device_id: 2 保修到什么时候", "2"),
    ("device_id: 3 的故障严重度如何", "3"),
]

WRITE_TASKS = [
    "device_id: 1 HC200 通信异常，请帮我创建工单",
    "device_id: 2 SC100 采集异常，申请维修",
    "device_id: 3 通道无数据，帮我报修",
    "device_id: 1 现场设备断连，需要开单处理",
]

VAGUE_TASKS = ["设备坏了怎么办", "帮我看看设备"]

MISSING_TASKS = ["device_id: 99999 查询设备状态", "device_id: 88888 创建工单"]


def main() -> int:
    results = []
    with httpx.Client(base_url=BASE, timeout=40.0) as client:
        login = client.post("/api/flowai/auth/login", json={"username": "admin", "password": PASSWORD})
        login.raise_for_status()
        headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}

        session = client.post(f"/api/flowai/apps/{SLUG}/sessions", headers=headers)
        session.raise_for_status()
        conversation_id = session.json()["data"]["conversation_id"]

        def ask(text: str) -> dict:
            response = client.post(
                f"/api/flowai/sessions/{conversation_id}/messages",
                json={"content": text},
                headers=headers,
            )
            body = response.json()
            return {"http": response.status_code, **body.get("data", {})}

        for index, (text, device_id) in enumerate(READ_TASKS, start=1):
            data = ask(text)
            ok = data.get("status") == "SUCCEEDED" and f"DEV-SYN-{int(device_id):04d}" in (data.get("message") or "")
            results.append({"kind": "read", "index": index, "ok": ok, "status": data.get("status"), "text": text})

        for index, text in enumerate(WRITE_TASKS, start=1):
            data = ask(text)
            ok = data.get("status") == "WAITING_CONFIRMATION" and bool(data.get("confirmation_token"))
            if ok:
                client.post(
                    f"/api/flowai/executions/{data['execution_id']}/reject",
                    headers=headers,
                )
            results.append({"kind": "write", "index": index, "ok": ok, "status": data.get("status"), "text": text})

        for index, text in enumerate(VAGUE_TASKS, start=1):
            data = ask(text)
            ok = data.get("status") == "SUCCEEDED" and "未识别到设备" in (data.get("message") or "")
            results.append({"kind": "vague", "index": index, "ok": ok, "status": data.get("status"), "text": text})

        for index, text in enumerate(MISSING_TASKS, start=1):
            data = ask(text)
            ok = data.get("status") in {"FAILED", "SUCCEEDED", "WAITING_CONFIRMATION"} and not data.get("result")
            results.append({"kind": "missing", "index": index, "ok": ok, "status": data.get("status"), "text": text})

    total = len(results)
    passed = len([item for item in results if item["ok"]])
    rate = passed / total if total else 0.0
    by_kind: dict[str, dict[str, int]] = {}
    for item in results:
        bucket = by_kind.setdefault(item["kind"], {"pass": 0, "total": 0})
        bucket["total"] += 1
        if item["ok"]:
            bucket["pass"] += 1

    report = ROOT / ".tmp" / f"ACC-04-Agent任务集-{datetime.now():%Y%m%d}.md"
    lines = [
        f"# ACC-04 Agent 任务集报告（{datetime.now():%Y-%m-%d %H:%M}）",
        "",
        f"- 入口：{BASE}；应用：{SLUG}",
        f"- 任务数：{total}；通过：{passed}；成功率：**{rate * 100:.1f}%**（门槛 ≥95%）",
        f"- 结论：**{'PASS' if rate >= 0.95 else 'FAIL'}**",
        "",
        "| 类别 | 通过/总数 |",
        "|---|---|",
    ]
    for kind, bucket in by_kind.items():
        lines.append(f"| {kind} | {bucket['pass']}/{bucket['total']} |")
    lines += ["", "| # | 类别 | 状态 | 结果 | 输入 |", "|---|---|---|---|---|"]
    for item in results:
        lines.append(
            f"| {item['index']} | {item['kind']} | {item['status']} | "
            f"{'PASS' if item['ok'] else 'FAIL'} | {item['text']} |"
        )
    lines += ["", "```json", json.dumps(results, ensure_ascii=False, indent=2), "```"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"total": total, "passed": passed, "rate": round(rate, 4), "by_kind": by_kind}, ensure_ascii=False))
    print(f"RESULT {'PASS' if rate >= 0.95 else 'FAIL'} report={report}")
    return 0 if rate >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())