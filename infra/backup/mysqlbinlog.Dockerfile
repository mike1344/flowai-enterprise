# PITR 工具镜像脚手架（CR-007）——**未在本机验证**
#
# 背景：官方 mysql:8.4 镜像不含 mysqlbinlog，binlog 重放无法执行。
# 本镜像用 Debian 的客户端包提供 binlog 读取工具；Debian bookworm 的
# default-mysql-client 实际是 MariaDB 客户端，二进制名为 mariadb-binlog，
# 这里补一个 mysqlbinlog 软链，便于 pitr-drill.ps1 直接调用。
#
# 使用前必须验证：mariadb-binlog 能否正确解析目标 MySQL 8.4 的 binlog。
#   docker build -f infra/backup/mysqlbinlog.Dockerfile -t flowai-ops-mysqlbinlog .
#   docker run --rm -v F:/Y1/.tmp:/w flowai-ops-mysqlbinlog \
#       mysqlbinlog /w/incr.binlog | head
# 若解析失败，改用 MySQL 官方客户端（repo.mysql.com 的 mysql-community-client）
# 或 Percona 的 mysqlbinlog，再跑：
#   powershell.exe -NoProfile -File infra\backup\pitr-drill.ps1 -Image flowai-ops-mysqlbinlog

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-mysql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && (command -v mariadb-binlog >/dev/null 2>&1 && ln -sf /usr/bin/mariadb-binlog /usr/bin/mysqlbinlog || true)

ENTRYPOINT ["mysqlbinlog"]