# 备份：两个 MySQL 库 + ChromaDB 持久数据（docs/08 §4）
# 用法：pwsh -File infra/backup/backup.ps1
param(
    [string]$ComposeDir = (Resolve-Path "$PSScriptRoot\..\compose").Path,
    [string]$OutDir = (Join-Path $PSScriptRoot "out")
)

$ErrorActionPreference = 'Continue'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $OutDir $stamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

Push-Location $ComposeDir
try {
    $rootPassword = (Get-Content .env | Where-Object { $_ -match '^MYSQL_ROOT_PASSWORD=' }) -replace '^MYSQL_ROOT_PASSWORD=', ''
    $flowaiDb = (Get-Content .env | Where-Object { $_ -match '^FLOWAI_DB_NAME=' }) -replace '^FLOWAI_DB_NAME=', ''
    $industrialDb = (Get-Content .env | Where-Object { $_ -match '^INDUSTRIAL_DB_NAME=' }) -replace '^INDUSTRIAL_DB_NAME=', ''
    if (-not $flowaiDb) { $flowaiDb = 'flowai_db' }
    if (-not $industrialDb) { $industrialDb = 'industrial_db' }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($db in @($flowaiDb, $industrialDb)) {
        $sql = & docker compose exec -T mysql sh -c "mysqldump -uroot -p$rootPassword --single-transaction --routines --triggers $db" 2>$null
        if ($LASTEXITCODE -ne 0) { throw "mysqldump failed for $db" }
        $sql | Set-Content -Encoding UTF8 (Join-Path $target "$db.sql")
    }
    # 增量恢复基准：记录当前 binlog 位点（PITR 从这里开始重放）
    $binlogRaw = & docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword -N -e 'SHOW BINARY LOG STATUS'" 2>$null
    $binlogPosition = ($binlogRaw | Select-Object -First 1)

    # ChromaDB 持久卷（索引数据）
    & docker compose cp chromadb:/data (Join-Path $target 'chroma-data') 2>$null
    $sw.Stop()

    $manifest = [ordered]@{
        created_at      = (Get-Date).ToString('o')
        duration_seconds= [math]::Round($sw.Elapsed.TotalSeconds, 2)
        databases       = @($flowaiDb, $industrialDb)
        chroma_copied   = Test-Path (Join-Path $target 'chroma-data')
        binlog_position = $binlogPosition
        directory       = $target
    }
    $manifest | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $target 'manifest.json')
    Write-Output "BACKUP_OK $target"
    $manifest | ConvertTo-Json -Compress
}
finally {
    Pop-Location
}