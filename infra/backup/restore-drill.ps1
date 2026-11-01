# 恢复演练：把备份恢复到独立 scratch 库并核对关键计数（不覆盖生产库）
# 用法：pwsh -File infra/backup/restore-drill.ps1 -BackupDir <backup folder>
param(
    [Parameter(Mandatory = $true)][string]$BackupDir,
    [string]$ComposeDir = (Resolve-Path "$PSScriptRoot\..\compose").Path
)

$ErrorActionPreference = 'Continue'
Push-Location $ComposeDir
try {
    $rootPassword = (Get-Content .env | Where-Object { $_ -match '^MYSQL_ROOT_PASSWORD=' }) -replace '^MYSQL_ROOT_PASSWORD=', ''
    $flowaiScratch = 'flowai_db_restore'
    $industrialScratch = 'industrial_db_restore'

    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $null = docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword -e 'DROP DATABASE IF EXISTS $flowaiScratch; CREATE DATABASE $flowaiScratch CHARACTER SET utf8mb4;'"
    $null = docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword -e 'DROP DATABASE IF EXISTS $industrialScratch; CREATE DATABASE $industrialScratch CHARACTER SET utf8mb4;'"

    docker compose cp (Join-Path $BackupDir 'flowai_db.sql') mysql:/tmp/flowai_db.sql | Out-Null
    docker compose cp (Join-Path $BackupDir 'industrial_db.sql') mysql:/tmp/industrial_db.sql | Out-Null
    $null = docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword $flowaiScratch < /tmp/flowai_db.sql"
    if ($LASTEXITCODE -ne 0) { throw 'restore flowai_db failed' }
    $null = docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword $industrialScratch < /tmp/industrial_db.sql"
    if ($LASTEXITCODE -ne 0) { throw 'restore industrial_db failed' }

    $checks = @(
        @($flowaiScratch, 'app_user'),
        @($flowaiScratch, 'ai_application'),
        @($flowaiScratch, 'application_version'),
        @($flowaiScratch, 'knowledge_base'),
        @($flowaiScratch, 'document'),
        @($flowaiScratch, 'document_chunk'),
        @($industrialScratch, 'customer'),
        @($industrialScratch, 'device'),
        @($industrialScratch, 'repair_ticket'),
        @($industrialScratch, 'ticket_action')
    )
    $sw.Stop()
    Write-Output 'RESTORED_COUNTS'
    foreach ($pair in $checks) {
        $dbName = $pair[0]
        $table = $pair[1]
        $value = & docker compose exec -T mysql sh -c "mysql -uroot -p$rootPassword -N -B -e 'SELECT COUNT(*) FROM $dbName.$table;'" 2>$null
        Write-Output ("{0}.{1}={2}" -f $dbName, $table, ($value -join '').Trim())
    }
    Write-Output ("RESTORE_SECONDS {0}" -f [math]::Round($sw.Elapsed.TotalSeconds, 2))
}
finally {
    Pop-Location
}