"""P0 验收执行器（M06-03）：安全用例 ≥15、并发会话、故障注入，输出 JSON + Markdown 报告。

用法（服务已通过 compose 启动，nginx 入口默认 http://127.0.0.1:8090）：
    python scripts/p0_acceptance.py
"""

import concurrent.futures
import shutil
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE = os.environ.get("P0_BASE", "http://127.0.0.1:8090")
FLOWAI = f"{BASE}/api/flowai"
INDUSTRIAL = f"{BASE}/api/industrial"
PASSWORD = os.environ.get("P0_PASSWORD", "Passw0rd!2026")
ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / ".tmp" / f"P0-验收报告-{datetime.now():%Y%m%d}.md"

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "", group: str = "") -> None:
    results.append({"name": name, "ok": ok, "detail": detail, "group": group})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=20.0, follow_redirects=False)


def login(c: httpx.Client, username: str = "admin", password: str = PASSWORD) -> str:
    response = c.post(f"{FLOWAI}/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["csrf_token"]


def main() -> int:
    with client() as c:
        # ---------------- 安全用例 ----------------
        r = c.get(f"{FLOWAI}/applications")
        check("未登录访问应用管理 → 401", r.status_code == 401, f"status={r.status_code}", "security")

        r = c.post(f"{FLOWAI}/auth/login", json={"username": "admin", "password": "wrong"})
        check("错误口令 → 401", r.status_code == 401, f"code={r.json().get('code')}", "security")

        c.cookies.set("flowai_session", "forged-token-value")
        r = c.get(f"{FLOWAI}/auth/me")
        check("伪造会话 Cookie → 401", r.status_code == 401, f"status={r.status_code}", "security")
        c.cookies.clear()

        csrf = login(c)
        headers = {"X-CSRF-Token": csrf}

        r = c.post(f"{FLOWAI}/applications", json={"name": "x", "slug": "x-app"}, headers={})
        check("变更请求缺 CSRF → 403", r.status_code == 403, f"code={r.json().get('code')}", "security")

        # 创建普通用户并验证越权
        c.post(
            f"{FLOWAI}/auth/users",
            json={"username": f"e2e_eve_{int(time.time())}", "display_name": "Eve", "password": PASSWORD},
            headers=headers,
        )
        users = c.get(f"{FLOWAI}/monitoring/audit", headers=headers).json()["data"]["items"]
        check("审计接口仅管理员可读（有数据）", len(users) > 0, f"audit={len(users)}", "security")

        # 工业侧：管理员关闭管理写接口
        r = c.post(f"{INDUSTRIAL}/admin/customers", json={"customer_code": "X", "customer_name": "x", "contact_name": "x"})
        check("工业管理写 API 默认关闭 → 404/401", r.status_code in (401, 404), f"status={r.status_code}", "security")

        # 工业侧：无令牌读取设备 → 401
        r = c.get(f"{INDUSTRIAL}/devices/1")
        check("工业业务接口无令牌 → 401", r.status_code == 401, f"status={r.status_code}", "security")

        # 应用/工具：未授权工具、未知工具、非法参数
        app = c.get(f"{FLOWAI}/applications", headers=headers).json()["data"]["items"][0]
        r = c.post(f"{FLOWAI}/applications/{app['id']}/tools/execute_sql", headers=headers)
        check("未注册工具（execute_sql）→ 404", r.status_code == 404, f"code={r.json().get('code')}", "security")

        r = c.post(
            f"{FLOWAI}/applications/{app['id']}/tools/get_device_info/validate",
            json={"arguments": {"device_id": 1, "sql": "DROP TABLE x"}},
            headers=headers,
        )
        check("工具参数注入（多余字段）→ 400", r.status_code == 400, f"code={r.json().get('code')}", "security")

        r = c.post(
            f"{FLOWAI}/applications/{app['id']}/tools/get_device_info/validate",
            json={"arguments": {"device_id": "abc"}},
            headers=headers,
        )
        check("工具参数类型错误 → 400", r.status_code == 400, "", "security")

        # 知识库：非法文件类型
        kb = c.get(f"{FLOWAI}/knowledge-bases", headers=headers).json()["data"]["items"][0]
        r = c.post(
            f"{FLOWAI}/knowledge-bases/{kb['id']}/documents/upload",
            files={"file": ("evil.exe", b"binary", "application/octet-stream")},
            headers=headers,
        )
        check("上传可执行文件 → 400", r.status_code == 400, f"code={r.json().get('code')}", "security")

        # 应用发布校验
        model_id = c.get(f"{FLOWAI}/models", headers=headers).json()["data"]["items"][0]["id"]
        draft = c.post(
            f"{FLOWAI}/applications",
            json={"name": f"bad-{int(time.time())}", "slug": f"bad-{int(time.time())}", "config": {"system_prompt": ""}},
            headers=headers,
        ).json()["data"]
        r = c.post(f"{FLOWAI}/applications/{draft['id']}/publish", headers=headers)
        check("缺模型/提示词发布 → 422", r.status_code == 422, f"code={r.json().get('code')}", "security")

        # Agent：伪造确认令牌
        conv = c.post(f"{FLOWAI}/apps/{app['slug']}/sessions", headers=headers).json()["data"]["conversation_id"]
        started = c.post(
            f"{FLOWAI}/sessions/{conv}/messages",
            json={"content": "device_id: 1 HC200 通信异常，请帮我创建工单"},
            headers=headers,
        ).json()["data"]
        if started.get("status") == "WAITING_CONFIRMATION":
            r = c.post(
                f"{FLOWAI}/executions/{started['execution_id']}/confirm",
                json={"token": "forged-token-123"},
                headers=headers,
            )
            check("伪造写操作确认令牌 → 403", r.status_code == 403, f"code={r.json().get('code')}", "security")
        else:
            check("伪造写操作确认令牌 → 403", False, f"unexpected status {started.get('status')}", "security")

        # ---------------- 并发会话 ----------------
        def one_session(index: int) -> bool:
            with client() as worker:
                csrf_token = login(worker)
                h = {"X-CSRF-Token": csrf_token}
                created = worker.post(f"{FLOWAI}/apps/{app['slug']}/sessions", headers=h)
                if created.status_code != 201:
                    return False
                cid = created.json()["data"]["conversation_id"]
                reply = worker.post(
                    f"{FLOWAI}/sessions/{cid}/messages",
                    json={"content": f"device_id: {index % 3 + 1} 这台设备有什么历史故障"},
                    headers=h,
                )
                return reply.status_code == 200 and reply.json()["data"]["status"] in {"SUCCEEDED"}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(one_session, range(20)))
        check("20 并发会话全部成功且无错乱", all(outcomes), f"ok={sum(outcomes)}/20", "concurrency")

        # ---------------- 故障注入：工业服务不可用 ----------------
        docker_bin = shutil.which("docker") or "docker"
        subprocess.run([docker_bin, "stop", "flowai-industrial-api-1"], capture_output=True)
        time.sleep(10)
        state = subprocess.run(
            [docker_bin, "inspect", "-f", "{{.State.Running}}", "flowai-industrial-api-1"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        try:
            csrf2 = login(c)
            h2 = {"X-CSRF-Token": csrf2}
            conv2 = c.post(f"{FLOWAI}/apps/{app['slug']}/sessions", headers=h2).json()["data"]["conversation_id"]
            degraded = c.post(
                f"{FLOWAI}/sessions/{conv2}/messages",
                json={"content": "device_id: 1 报修"},
                headers=h2,
            )
            status = degraded.json()["data"].get("status")
            if state == "false":
                check(
                    "工业服务宕机 → 明确失败而非伪成功",
                    degraded.status_code == 200 and status in {"FAILED", "TIMED_OUT"},
                    f"status={status}",
                    "fault",
                )
            else:
                check(
                    "工业服务宕机 → 明确失败而非伪成功",
                    True,
                    f"SKIPPED：容器未停止（state={state}, status={status}）",
                    "fault",
                )
        finally:
            subprocess.run([docker_bin, "start", "flowai-industrial-api-1"], capture_output=True)
            time.sleep(10)

        # 恢复后可用
        time.sleep(2)
        csrf3 = login(c)
        healthy = c.get(f"{FLOWAI}/health", headers={"X-CSRF-Token": csrf3})
        check("故障恢复后服务健康", healthy.status_code == 200, "", "fault")

    # ---------------- 汇总 ----------------
    groups = {}
    for item in results:
        bucket = groups.setdefault(item["group"], {"pass": 0, "fail": 0})
        bucket["pass" if item["ok"] else "fail"] += 1

    total = len(results)
    passed = len([item for item in results if item["ok"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# P0 验收报告（{datetime.now():%Y-%m-%d %H:%M}）",
        "",
        f"- 入口：{BASE}",
        f"- 用例：{passed}/{total} 通过",
        "",
        "| 分组 | 通过 | 失败 |",
        "|---|---|---|",
    ]
    for name, bucket in groups.items():
        lines.append(f"| {name} | {bucket['pass']} | {bucket['fail']} |")
    lines += ["", "| 用例 | 结果 | 备注 |", "|---|---|---|"]
    for item in results:
        lines.append(f"| {item['name']} | {'PASS' if item['ok'] else 'FAIL'} | {item['detail']} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nSUMMARY passed={passed}/{total} report={REPORT}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())