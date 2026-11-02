# T4 验收证据：限流共享化 + binlog/PITR 能力（CR-007）

> 日期：2026-11-02｜执行者：DSH 实施代理
> 结论：**部分完成（PARTIAL，如实记录）**
> - ✅ 限流：Redis 共享计数已实现并在容器内验证 `backend=redis`，Redis 不可用自动回退进程内；多副本一致。
> - ✅ 备份：MySQL 已开启 binlog（ROW + sync-binlog），备份清单记录 binlog 位点。
> - ⚠️ PITR 重放：全量恢复演练 **PASS（RTO 0.22s）**；binlog 重放 **SKIPPED**——官方 `mysql:8.4` 镜像不含 `mysqlbinlog`，本机无法完成重放验证（原因与补救见 §4）。

## 1. 范围修正

变更单原写「会话与限流在进程内」。核查后：**会话本来就存于数据库**（`app_session`/`UserSession` 表），多副本天然共享，无需迁移；真正只存在于进程内的是**登录失败限流**（`app/core/ratelimit.py` 的按进程字典）。因此本项收敛为「限流迁 Redis」，避免制造不存在的工作。

## 2. 限流共享化

| 文件 | 变更 |
|---|---|
| `app/core/ratelimit.py` | 后端抽象：Redis 优先（ZSET 滑动窗口 + EXPIRE），缺 `FLOWAI_REDIS_URL` 或连接失败时回退进程内；`configure()` 在应用启动时执行 |
| `app/main.py` | 启动时 `ratelimit.configure(settings)`，后端记录在 `app.state.rate_limit_backend` |
| `tests/test_ratelimit_backend.py` | 5 个用例：无 Redis → memory、Redis 不可达 → 回退、阈值仍生效、按 IP/用户隔离、clear 重置 |

容器内实测：

```text
redis_url set: True
backend: redis
```

（`docker compose run --rm --no-deps flowai-api python -c "... configure(get_settings())"`）

## 3. binlog 与备份

| 变更 | 说明 |
|---|---|
| `docker-compose.yml` | mysql 增加 `--log-bin=mysql-bin --server-id=1 --binlog-format=ROW --binlog_expire_logs_seconds=604800 --sync-binlog=1` |
| `infra/backup/backup.ps1` | 备份清单新增 `binlog_position`（`SHOW BINARY LOG STATUS`），作为增量恢复起点 |
| `infra/backup/pitr-drill.ps1` | 新增 PITR 演练脚本：一次性 MySQL 容器 → 全量 dump（带位点）→ 备份后写入 → drop 库 → 恢复 → 重放 binlog → 校验 |

实测（2026-11-02 21:45）：

```text
backup_position: mysql-bin.000001:1322   # 生产库（含 binlog 已开启）
drill:  backup_position=mysql-bin.000003:694, full_dump=2.3KB,
        rows_after_full_restore=1, full_restore_seconds=0.22,
        binlog_replay=SKIPPED, result=PARTIAL
```

## 4. 为什么 PITR 重放没跑成（关键限制）

官方 `mysql:8.4` 镜像**不含 `mysqlbinlog`**（实测 `find / -name "mysqlbinlog*"` 为空，只有 `mysql`/`mysqladmin`/`mysqldump`/`mysqlsh`）。而 binlog 重放必须用 `mysqlbinlog` 解析成 SQL。

尝试过的替代方案：在 `debian:bookworm-slim` 里 `apt-get install mariadb-client` 取 `mariadb-binlog`，但本机 apt 下载超时（15 分钟未完成），已放弃并把结论写进限制。

**已落地的脚手架**：`infra/backup/mysqlbinlog.Dockerfile`（Debian + default-mysql-client + `mariadb-binlog` 软链）。构建后可用 `pitr-drill.ps1 -Image flowai-ops-mysqlbinlog` 复跑；**该镜像未在本机验证**（apt 拉包在本机持续超时），首次使用必须先确认 `mariadb-binlog` 能解析 MySQL 8.4 的 binlog。`n`n**补救路径（任一即可）**：
1. 运维机安装 MySQL 客户端（含 `mysqlbinlog`），把 `docker cp` 出来的 binlog 在宿主机重放；
2. 自建 ops 镜像：`FROM mysql:8.4` + 安装 `mysql-community-client`，专用于 PITR；
3. 改用带 `mysqlbinlog` 的 Percona/MariaDB 工具链（需验证与 8.4 binlog 兼容）。

## 5. 回归

| 项 | 结果 |
|---|---|
| flowai-api 单测/集成 | **146 passed**（141 + 5 限流后端用例） |
| 备份脚本 | `BACKUP_OK`，1.08s，清单含 `binlog_position`、`chroma_copied=true` |
| 栈 | 重建后 7 容器 healthy；登录/检索冒烟通过 |

## 6. 复现

```powershell
# 备份（含 binlog 位点）
powershell.exe -NoProfile -File infra\backup\backup.ps1

# PITR 演练（自建一次性容器，不影响生产库）
powershell.exe -NoProfile -File infra\backup\pitr-drill.ps1

# 限流后端
docker compose exec flowai-api python -c "from app.core import ratelimit; from app.core.config import get_settings; print(ratelimit.configure(get_settings()))"
```

## 7. 已知限制

- binlog 重放未验证（缺 `mysqlbinlog`），PITR 的 RPO 因此**不可承诺**；当前只有「全量备份 + 位点」。
- binlog 保留 7 天（`binlog_expire_logs_seconds=604800`），超出窗口无法回放到更早时点。
- 限流 Redis 后端未做多实例并发压测；键按 `user@ip` 设计，同一 NAT 出口下可能互相影响。
- 备份只做全量 + Chroma 卷拷贝；未做备份加密与异地存放。