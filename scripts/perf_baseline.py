"""V1.3 性能基线：模型路径与写路径（CR-004 / T1）。

ACC-09（perf_smoke.py）只覆盖读路径；本脚本补上两条真实成本的路径：
  - 模型路径：POST /sessions/{id}/messages（RAG + 真实 LLM + 工具调用）
  - 写路径：模型给出工单草稿后 POST /executions/{id}/confirm（写业务库）

用法：
    python scripts/perf_baseline.py                      # 默认 1/2/4 并发，每档 12 次
    python scripts/perf_baseline.py --requests 6 --levels 1,2
    python scripts/perf_baseline.py --dry-run            # 只校验登录与建会话

输出：
    docs/acceptance/V1.3-性能基线-YYYYMMDD.md（Markdown 表格 + JSON）
"""

import argparse
import concurrent.futures
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = os.environ.get("PERF_PASSWORD", "Passw0rd!2026")

MODEL_QUESTION = "device_id: 1 这台设备有什么历史故障？"
WRITE_QUESTION = "device_id: 1 HC200 通信异常，请帮我创建工单"

# 冻结的 SLO 门槛（本机单机 Compose 环境，非生产承诺）
SLO = {"model_p95_ms": 6000.0, "write_p95_ms": 800.0, "error_rate": 0.01}


class Session:
    """一个登录后的客户端（每线程一个，避免 Cookie 串味）。"""

    def __init__(self, base: str):
        self.client = httpx.Client(base_url=base, timeout=60.0)
        response = self.client.post(
            "/api/flowai/auth/login", json={"username": "admin", "password": PASSWORD}
        )
        response.raise_for_status()
        self.csrf = response.json()["data"]["csrf_token"]
        self.headers = {"X-CSRF-Token": self.csrf}

    def close(self) -> None:
        self.client.close()


def open_session(session: Session, slug: str) -> str:
    response = session.client.post(f"/api/flowai/apps/{slug}/sessions", headers=session.headers)
    response.raise_for_status()
    return response.json()["data"]["conversation_id"]


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(p / 100 * len(ordered) + 0.5)) - 1))
    return round(ordered[index], 2)


def summarize(label: str, latencies: list[float], errors: int, wall: float) -> dict:
    return {
        "label": label,
        "requests": len(latencies),
        "errors": errors,
        "error_rate": round(errors / max(1, len(latencies) + errors), 4),
        "rps": round(len(latencies) / wall, 2) if wall else 0.0,
        "p50_ms": pct(latencies, 50),
        "p95_ms": pct(latencies, 95),
        "p99_ms": pct(latencies, 99),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "mean_ms": round(statistics.fmean(latencies), 2) if latencies else 0.0,
    }


def model_iteration(base: str, slug: str) -> tuple[bool, float]:
    session = Session(base)
    try:
        conversation = open_session(session, slug)
        started = time.perf_counter()
        response = session.client.post(
            f"/api/flowai/sessions/{conversation}/messages",
            json={"content": MODEL_QUESTION},
            headers=session.headers,
        )
        elapsed = (time.perf_counter() - started) * 1000
        ok = response.status_code == 200 and response.json()["data"]["status"] == "SUCCEEDED"
        return ok, elapsed
    except Exception:  # noqa: BLE001 - 压测脚本按失败计数
        return False, 0.0
    finally:
        session.close()


def write_iteration(base: str, slug: str) -> tuple[bool, float]:
    """草稿阶段不计入写路径时延，只计 confirm（真正落库）的那一次调用。"""
    session = Session(base)
    try:
        conversation = open_session(session, slug)
        draft = session.client.post(
            f"/api/flowai/sessions/{conversation}/messages",
            json={"content": WRITE_QUESTION},
            headers=session.headers,
        )
        if draft.status_code != 200:
            return False, 0.0
        data = draft.json()["data"]
        if data.get("status") != "WAITING_CONFIRMATION":
            return False, 0.0
        started = time.perf_counter()
        response = session.client.post(
            f"/api/flowai/executions/{data['execution_id']}/confirm",
            json={"token": data["confirmation_token"]},
            headers=session.headers,
        )
        elapsed = (time.perf_counter() - started) * 1000
        return response.status_code == 200, elapsed
    except Exception:  # noqa: BLE001
        return False, 0.0
    finally:
        session.close()


def run_level(base: str, slug: str, concurrency: int, requests: int, kind: str) -> dict:
    iterate = model_iteration if kind == "model" else write_iteration
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        outcomes = list(pool.map(lambda _: iterate(base, slug), range(requests)))
    wall = time.perf_counter() - started
    latencies = [elapsed for ok, elapsed in outcomes if ok]
    errors = sum(1 for ok, _ in outcomes if not ok)
    label = f"{'模型路径' if kind == 'model' else '写路径'} c={concurrency}"
    return summarize(label, latencies, errors, wall)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("PERF_BASE", "http://127.0.0.1:8090"))
    parser.add_argument("--slug", default="service-agent")
    parser.add_argument("--levels", default="1,2,4")
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default=str(ROOT / "docs" / "acceptance"))
    args = parser.parse_args()

    levels = [int(item) for item in args.levels.split(",") if item.strip()]
    probe = Session(args.base)
    conversation = open_session(probe, args.slug)
    probe.close()
    print(f"预检通过：登录成功，会话 {conversation}（app /apps/{args.slug}）")
    if args.dry_run:
        print("DRY RUN：仅校验连通性，不发起模型调用")
        return 0

    phases: list[dict] = []
    for kind in ("model", "write"):
        for level in levels:
            phase = run_level(args.base, args.slug, level, args.requests, kind)
            phases.append(phase)
            print(
                f"{phase['label']}: n={phase['requests']} err={phase['error_rate'] * 100:.1f}% "
                f"rps={phase['rps']} p50={phase['p50_ms']}ms p95={phase['p95_ms']}ms p99={phase['p99_ms']}ms"
            )

    model_phases = [p for p in phases if p["label"].startswith("模型")]
    write_phases = [p for p in phases if p["label"].startswith("写路径")]
    worst_model = max((p["p95_ms"] for p in model_phases), default=0.0)
    worst_write = max((p["p95_ms"] for p in write_phases), default=0.0)
    error_rate = max((p["error_rate"] for p in phases), default=0.0)
    passed = (
        worst_model <= SLO["model_p95_ms"]
        and worst_write <= SLO["write_p95_ms"]
        and error_rate <= SLO["error_rate"]
    )

    report = Path(args.out_dir) / f"V1.3-性能基线-{datetime.now():%Y%m%d}.md"
    lines = [
        f"# V1.3 性能基线（模型路径 / 写路径）— {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"- 入口：{args.base}（Docker Compose 单机，Windows 11 本机）",
        f"- 每档请求数：{args.requests}；并发档位：{', '.join(str(x) for x in levels)}",
        f"- 冻结门槛：模型路径 P95 ≤ {SLO['model_p95_ms']}ms、写路径 P95 ≤ {SLO['write_p95_ms']}ms、错误率 ≤ {SLO['error_rate'] * 100:.0f}%",
        f"- 结论：**{'PASS' if passed else 'FAIL'}**",
        "",
        "| 阶段 | 请求数 | 并发 | RPS | 错误率 | P50 | P95 | P99 | Max |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for phase in phases:
        concurrency = phase["label"].split("c=")[-1]
        lines.append(
            f"| {phase['label'].split(' c=')[0]} | {phase['requests']} | {concurrency} | {phase['rps']} | "
            f"{phase['error_rate'] * 100:.1f}% | {phase['p50_ms']}ms | {phase['p95_ms']}ms | "
            f"{phase['p99_ms']}ms | {phase['max_ms']}ms |"
        )
    lines += [
        "",
        "> 写路径只统计 `POST /executions/{id}/confirm`（真正落库那一次）；草稿生成属模型路径，不计入。",
        "> 模型路径含 RAG 检索、真实 LLM（DeepSeek）与工业 API 工具调用，时延由外部模型主导。",
        "> 本机单机环境实测，不构成生产 SLA；生产需在客户环境复测。",
        "",
        "```json",
        json.dumps(phases, ensure_ascii=False, indent=2),
        "```",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"RESULT {'PASS' if passed else 'FAIL'} report={report}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())