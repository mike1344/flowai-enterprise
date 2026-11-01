"""ACC-09 性能冒烟：并发读取业务 API，统计 P50/P95/P99、吞吐与错误率。

用法：python scripts/perf_smoke.py [--base http://127.0.0.1:8090] [--concurrency 20] [--duration 30]
输出：docs/acceptance/ACC-09-性能报告-YYYYMMDD.md
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


def login(base: str) -> tuple[httpx.Client, dict[str, str], str]:
    client = httpx.Client(base_url=base, timeout=20.0)
    response = client.post(
        "/api/flowai/auth/login", json={"username": "admin", "password": PASSWORD}
    )
    response.raise_for_status()
    data = response.json()["data"]
    return client, {"X-CSRF-Token": data["csrf_token"]}, data["csrf_token"]


def timed(client: httpx.Client, method: str, path: str, headers: dict, body: dict | None = None):
    started = time.perf_counter()
    try:
        if method == "GET":
            response = client.get(path, headers=headers)
        else:
            response = client.post(path, headers=headers, json=body)
        elapsed = (time.perf_counter() - started) * 1000
        return response.status_code, elapsed
    except httpx.HTTPError:
        return 0, (time.perf_counter() - started) * 1000


def run_phase(base: str, concurrency: int, duration: float, label: str, path: str, method: str = "GET"):
    client, headers, _ = login(base)
    stop_at = time.time() + duration
    results: list[tuple[int, float]] = []

    def worker() -> list[tuple[int, float]]:
        local: list[tuple[int, float]] = []
        with httpx.Client(base_url=base, timeout=20.0) as worker_client:
            while time.time() < stop_at:
                local.append(timed(worker_client, method, path, headers))
        return local

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(concurrency)]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    latencies = sorted(item[1] for item in results)
    total = len(latencies)
    errors = len([item for item in results if item[0] >= 500 or item[0] == 0])
    client.close()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        index = min(total - 1, max(0, int(round(p / 100 * total + 0.5)) - 1))
        return round(latencies[index], 2)

    return {
        "label": label,
        "path": f"{method} {path}",
        "concurrency": concurrency,
        "duration_seconds": duration,
        "requests": total,
        "rps": round(total / duration, 2),
        "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "p99_ms": pct(99),
        "max_ms": round(latencies[-1], 2) if latencies else 0.0,
        "mean_ms": round(statistics.fmean(latencies), 2) if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("PERF_BASE", "http://127.0.0.1:8090"))
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--duration", type=float, default=20.0)
    args = parser.parse_args()

    phases = [
        run_phase(args.base, args.concurrency, args.duration, "健康检查", "/api/flowai/health"),
        run_phase(args.base, args.concurrency, args.duration, "应用列表（含鉴权）", "/api/flowai/applications"),
        run_phase(args.base, args.concurrency, args.duration, "知识库列表", "/api/flowai/knowledge-bases"),
        run_phase(args.base, args.concurrency, args.duration, "工业设备查询（含服务令牌+业务鉴权）", "/api/industrial/devices/1"),
    ]

    target_p95 = 500.0
    passed = all(phase["p95_ms"] <= target_p95 and phase["error_rate"] <= 0.01 for phase in phases)

    report_path = ROOT / ".tmp" / f"ACC-09-性能报告-{datetime.now():%Y%m%d}.md"
    lines = [
        f"# ACC-09 性能冒烟报告（{datetime.now():%Y-%m-%d %H:%M}）",
        "",
        f"- 入口：{args.base}（Docker Compose 单机）",
        f"- 并发：{args.concurrency}；每阶段时长：{args.duration}s",
        "- 门槛：P95 ≤ 500ms（不含模型推理），错误率 ≤ 1%",
        f"- 结论：**{'PASS' if passed else 'FAIL'}**",
        "",
        "| 阶段 | 请求数 | RPS | 错误率 | P50 | P95 | P99 | Max |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for phase in phases:
        lines.append(
            f"| {phase['label']} | {phase['requests']} | {phase['rps']} | "
            f"{phase['error_rate'] * 100:.2f}% | {phase['p50_ms']}ms | {phase['p95_ms']}ms | "
            f"{phase['p99_ms']}ms | {phase['max_ms']}ms |"
        )
    lines += ["", "```json", json.dumps(phases, ensure_ascii=False, indent=2), "```"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for phase in phases:
        print(
            f"{phase['label']}: n={phase['requests']} rps={phase['rps']} "
            f"p95={phase['p95_ms']}ms err={phase['error_rate'] * 100:.2f}%"
        )
    print(f"RESULT {'PASS' if passed else 'FAIL'} report={report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())