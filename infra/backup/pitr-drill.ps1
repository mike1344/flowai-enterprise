# PITR drill (CR-007): full dump + binlog replay on a throwaway MySQL container.
# ASCII-only on purpose (Windows PowerShell 5.1 encoding safety).
#
# Usage:
#   powershell.exe -NoProfile -File infra\backup\pitr-drill.ps1
#
# Requires: docker. The replay half needs mysqlbinlog; the official mysql:8.4 image
# ships only mysql/mysqldump, so replay is reported SKIPPED and the drill ends PARTIAL.

param(
    [string]$Password = "DrillOnly!2026",
    [string]$Image = "mysql:8.4",
    # 可选：提供 mysqlbinlog 的工具镜像（服务端仍用 -Image）`n    # 例：percona/percona-server:8.4（自带 mysqlbinlog）；注意它不能当服务端用本脚本的 -Image
    [string]$BinlogImage = ""
)

$ErrorActionPreference = "Continue"
$name = "flowai-pitr-drill-" + (Get-Date -Format "yyyyMMddHHmmss")
$work = Join-Path $PSScriptRoot ("out\pitr-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $work | Out-Null

function Wait-MySql {
    param([string]$Container, [int]$TimeoutSeconds = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        docker exec $Container mysql -uroot "-p$Password" -N -e "SELECT 1;" *> $null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Sql {
    param([string]$Query)
    $raw = docker exec -i $name mysql -uroot "-p$Password" -N -e $Query 2>&1
    if ($LASTEXITCODE -ne 0) { throw "SQL failed: $Query" }
    $clean = $raw | Where-Object { $_ -notmatch "^mysql: \[Warning\]" -and $_.Trim() -ne "" }
    return (($clean -join "`n").Trim())
}

function Run-File {
    param([string]$Path)
    Get-Content -Raw $Path | docker exec -i $name mysql -uroot "-p$Password" 2>&1 | Out-Null
    return $LASTEXITCODE
}

try {
    Write-Host "== start scratch mysql (binlog on) =="
    docker run -d --name $name -e "MYSQL_ROOT_PASSWORD=$Password" -e "MYSQL_DATABASE=demo" $Image `
        --server-id=101 --log-bin=mysql-bin --binlog-format=ROW --sync-binlog=1 | Out-Null
    if (-not (Wait-MySql -Container $name)) { throw "scratch mysql did not become ready" }

    Write-Host "== seed before backup =="
    Sql "CREATE TABLE demo.orders (id INT PRIMARY KEY, amount INT, note VARCHAR(50));" | Out-Null
    Sql "INSERT INTO demo.orders VALUES (1, 100, 'before-backup');" | Out-Null

    Write-Host "== full backup (with binlog coordinates) =="
    $dumpFile = Join-Path $work "full.sql"
    docker exec $name mysqldump -uroot "-p$Password" --single-transaction --source-data=2 --databases demo 2>$null |
        Set-Content -Path $dumpFile -Encoding UTF8
    if (-not (Test-Path $dumpFile) -or (Get-Item $dumpFile).Length -lt 500) { throw "dump looks empty" }

    $header = Select-String -Path $dumpFile -Pattern "SOURCE_LOG_FILE|MASTER_LOG_FILE" | Select-Object -First 1
    if (-not $header) { throw "no binlog coordinates in dump header" }
    $logFile = ([regex]::Match($header.Line, "SOURCE_LOG_FILE='([^']+)'")).Groups[1].Value
    if (-not $logFile) { $logFile = ([regex]::Match($header.Line, "MASTER_LOG_FILE='([^']+)'")).Groups[1].Value }
    $logPos = ([regex]::Match($header.Line, "SOURCE_LOG_POS=(\d+)")).Groups[1].Value
    if (-not $logPos) { $logPos = ([regex]::Match($header.Line, "MASTER_LOG_POS=(\d+)")).Groups[1].Value }
    Write-Host ("   backup position = {0}:{1}" -f $logFile, $logPos)

    Write-Host "== changes after backup =="
    Sql "INSERT INTO demo.orders VALUES (2, 250, 'after-backup');" | Out-Null
    Sql "UPDATE demo.orders SET amount = 300 WHERE id = 2;" | Out-Null
    Sql "FLUSH BINARY LOGS;" | Out-Null

    Write-Host "== simulate disaster: drop database =="
    Sql "DROP DATABASE demo;" | Out-Null

    Write-Host "== restore full backup =="
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $restoreExit = Run-File -Path $dumpFile
    $sw.Stop()
    if ($restoreExit -ne 0) { throw "restore failed (exit $restoreExit)" }
    $rowsAfterDump = [int](Sql "SELECT COUNT(*) FROM demo.orders;")
    Write-Host ("   restored rows = {0} (RTO {1}s)" -f $rowsAfterDump, [math]::Round($sw.Elapsed.TotalSeconds, 2))

    Write-Host "== binlog replay (PITR) =="
    $hasBinlogTool = (docker exec $name sh -c "command -v mysqlbinlog" 2>$null)
    $externalTool = [bool]$BinlogImage
    $replayStatus = "SKIPPED"
    $replayDetail = "mysqlbinlog not shipped in image $Image"
    $row2Amount = 0

    if ($hasBinlogTool -or $externalTool) {
        $binlogFile = Join-Path $work "incr.binlog"
        $files = (docker exec $name sh -c "ls /var/lib/mysql/mysql-bin.0* | sort" 2>$null) -split "`n" |
            Where-Object { $_.Trim() }
        $targets = @()
        $started = $false
        foreach ($f in $files) {
            $leaf = Split-Path $f -Leaf
            if ($leaf -eq $logFile) { $started = $true }
            if ($started) { $targets += ("/var/lib/mysql/" + $leaf) }
        }
        if ($targets.Count -gt 0) {
            if ($hasBinlogTool) {
                $quoted = ($targets | ForEach-Object { "'" + $_ + "'" }) -join " "
                docker exec $name sh -c "mysqlbinlog --start-position=$logPos $quoted > /tmp/incr.binlog" | Out-Null
                docker cp "${name}:/tmp/incr.binlog" $binlogFile | Out-Null
            }
            else {
                # 服务端镜像没有工具：把 binlog 拷出来，交给 -BinlogImage 解析
                $binDir = Join-Path $work "binlogs"
                New-Item -ItemType Directory -Force -Path $binDir | Out-Null
                foreach ($t in $targets) { docker cp "${name}:$t" $binDir 2>$null | Out-Null }
                $mapped = (Get-ChildItem $binDir | Sort-Object Name | ForEach-Object { "/w/binlogs/" + $_.Name }) -join " "
                docker run --rm -v "${work}:/w" $BinlogImage sh -c "mysqlbinlog --start-position=$logPos $mapped > /w/incr.binlog" | Out-Null
            }
            $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
            $replayExit = Run-File -Path $binlogFile
            $sw2.Stop()
            $row2Amount = [int](Sql "SELECT amount FROM demo.orders WHERE id = 2;")
            $replayStatus = if ($replayExit -eq 0 -and $row2Amount -eq 300) { "PASS" } else { "FAIL" }
            $replayDetail = "replayed from $logFile`:$logPos in $([math]::Round($sw2.Elapsed.TotalSeconds,2))s"
        }
    }

    $count = [int](Sql "SELECT COUNT(*) FROM demo.orders;")
    $result = "PARTIAL"
    if ($replayStatus -eq "PASS" -and $count -eq 2) { $result = "PASS" }
    if ($replayStatus -eq "FAIL") { $result = "FAIL" }

    $summary = [ordered]@{
        drill = "PITR"
        backup_position = "$logFile`:$logPos"
        full_dump_kb = [math]::Round((Get-Item $dumpFile).Length / 1KB, 1)
        rows_after_full_restore = $rowsAfterDump
        rows_after_replay = $count
        row2_amount = $row2Amount
        full_restore_seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        binlog_replay = $replayStatus
        binlog_replay_detail = $replayDetail
        result = $result
        workdir = $work
    }
    $summary | ConvertTo-Json | Set-Content -Path (Join-Path $work "summary.json") -Encoding UTF8
    $summary | ConvertTo-Json
    if ($result -eq "FAIL") { exit 1 } else { exit 0 }
}
finally {
    docker rm -f $name 2>$null | Out-Null
}