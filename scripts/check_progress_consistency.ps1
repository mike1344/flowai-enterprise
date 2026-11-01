#requires -Version 5.1
<#
.SYNOPSIS
  FlowAI Enterprise V1.2 —— 进度四件套一致性校验器（审计工具，非产品代码）。

.DESCRIPTION
  校验 docs/13 与 docs/09 规定的进度治理约束，保证“看板 = 实际任务状态”：
    1. 任务集合一致：progress/任务进度.json、progress/任务总表.csv、
       progress/进度看板.html 内嵌 baseline、docs/12 清单 四向一致（29 项）。
    2. 字段一致：编号、名称、依赖、权重、优先级、验收标准、状态。
    3. 权重口径：合计 = 100，P0 = 80，P1 = 20。
    4. 依赖闭合：依赖均存在、无环、不依赖后续阶段（S0→S5 不得逆序）。
    5. 状态纪律：同一时刻最多一个 DOING；DONE 必须依赖全 DONE 且有验收证据；
       TESTED/DONE 必须有证据；READY 必须依赖已全部 DONE。
    6. docs/02 与 JSON 的依赖/验收标准逐条一致。

  退出码：0 = 全部通过；1 = 存在 FAIL。该脚本可反复运行，用于任务状态变更后的回归校验。

.PARAMETER Root
  仓库根目录，默认取脚本所在目录的父目录。

.EXAMPLE
  pwsh -NoProfile -File scripts/check_progress_consistency.ps1
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$failures = New-Object System.Collections.ArrayList
$passCount = 0

function Add-Fail {
    param([string]$Message)
    [void]$failures.Add($Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Add-Pass {
    param([string]$Message)
    $script:passCount = $script:passCount + 1
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Add-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

# ---------------------------------------------------------------- 读取输入
$jsonPath = Join-Path $Root 'progress\任务进度.json'
$csvPath  = Join-Path $Root 'progress\任务总表.csv'
$htmlPath = Join-Path $Root 'progress\进度看板.html'
$doc12Path = Join-Path $Root 'docs\12-项目进度看板与任务跟踪.md'
$doc02Path = Join-Path $Root 'docs\02-里程碑与任务依赖.md'

foreach ($p in @($jsonPath, $csvPath, $htmlPath, $doc12Path, $doc02Path)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Add-Fail "缺少文件：$p"
    }
}
if ($failures.Count -gt 0) {
    Write-Host "`n结论：FAIL（输入文件缺失，无法校验）" -ForegroundColor Red
    exit 1
}

$json = Get-Content -Raw -Encoding UTF8 -LiteralPath $jsonPath | ConvertFrom-Json
$csv  = Import-Csv -Encoding UTF8 -LiteralPath $csvPath
$html = Get-Content -Raw -Encoding UTF8 -LiteralPath $htmlPath
$doc12 = Get-Content -Raw -Encoding UTF8 -LiteralPath $doc12Path
$doc02 = Get-Content -Encoding UTF8 -LiteralPath $doc02Path

$startMarker = 'const baseline='
$endMarker   = ';const key='
$s = $html.IndexOf($startMarker)
$e = $html.IndexOf($endMarker, [Math]::Max($s, 0))
if ($s -lt 0 -or $e -lt 0) {
    Add-Fail '看板 HTML 中未找到内嵌 baseline JSON'
    $board = $null
} else {
    $rawBaseline = $html.Substring($s + $startMarker.Length, $e - $s - $startMarker.Length)
    try {
        $board = $rawBaseline | ConvertFrom-Json
    } catch {
        Add-Fail ('看板内嵌 baseline JSON 解析失败：' + $_.Exception.Message)
        $board = $null
    }
}

# ---------------------------------------------------------------- 1. 任务集合
$jsonIds = @($json.tasks | ForEach-Object { $_.id })
$csvIds  = @($csv | ForEach-Object { $_.'任务ID' })
$doc12Ids = @([regex]::Matches($doc12, '\*\*(M\d\d-\d\d)[^*]*\*\*') | ForEach-Object { $_.Groups[1].Value })

Add-Info ("JSON 任务数：" + $jsonIds.Count + "；CSV 行数：" + $csvIds.Count + "；docs/12 条目：" + $doc12Ids.Count)
if ($board -ne $null) { Add-Info ('看板 baseline 任务数：' + @($board.tasks).Count) }

if ($jsonIds.Count -eq 29) { Add-Pass 'JSON 任务总数为 29' } else { Add-Fail ('JSON 任务总数应为 29，实际 ' + $jsonIds.Count) }
if ($csvIds.Count -eq 29) { Add-Pass 'CSV 行数为 29' } else { Add-Fail ('CSV 行数应为 29，实际 ' + $csvIds.Count) }
if ($doc12Ids.Count -eq 29) { Add-Pass 'docs/12 任务条目为 29' } else { Add-Fail ('docs/12 任务条目应为 29，实际 ' + $doc12Ids.Count) }

$missingInCsv = @($jsonIds | Where-Object { $csvIds -notcontains $_ })
$extraInCsv   = @($csvIds | Where-Object { $jsonIds -notcontains $_ })
if ($missingInCsv.Count -eq 0 -and $extraInCsv.Count -eq 0) {
    Add-Pass 'JSON 与 CSV 任务集合一致'
} else {
    Add-Fail ('JSON/CSV 任务集合不一致；CSV 缺失 [' + ($missingInCsv -join ',') + ']；CSV 多余 [' + ($extraInCsv -join ',') + ']')
}

$missingInDoc12 = @($jsonIds | Where-Object { $doc12Ids -notcontains $_ })
$extraInDoc12   = @($doc12Ids | Where-Object { $jsonIds -notcontains $_ })
if ($missingInDoc12.Count -eq 0 -and $extraInDoc12.Count -eq 0) {
    Add-Pass 'JSON 与 docs/12 任务集合一致'
} else {
    Add-Fail ('JSON/docs12 任务集合不一致；docs12 缺失 [' + ($missingInDoc12 -join ',') + ']；docs12 多余 [' + ($extraInDoc12 -join ',') + ']')
}

if ($board -ne $null) {
    $boardIds = @($board.tasks | ForEach-Object { $_.id })
    $missingInBoard = @($jsonIds | Where-Object { $boardIds -notcontains $_ })
    $extraInBoard   = @($boardIds | Where-Object { $jsonIds -notcontains $_ })
    if ($missingInBoard.Count -eq 0 -and $extraInBoard.Count -eq 0) {
        Add-Pass 'JSON 与看板 baseline 任务集合一致'
    } else {
        Add-Fail ('JSON/看板任务集合不一致；看板缺失 [' + ($missingInBoard -join ',') + ']；看板多余 [' + ($extraInBoard -join ',') + ']')
    }
}

# ---------------------------------------------------------------- 2. 字段一致性
$fieldIssues = New-Object System.Collections.ArrayList
if ($board -ne $null) {
    foreach ($t in $json.tasks) {
        $b = $board.tasks | Where-Object { $_.id -eq $t.id } | Select-Object -First 1
        if ($b -eq $null) { continue }
        foreach ($f in @('title', 'status', 'acceptance', 'priority', 'weight', 'owner', 'started_at', 'finished_at', 'evidence', 'notes')) {
            if ([string]$b.$f -ne [string]$t.$f) {
                [void]$fieldIssues.Add($t.id + '.' + $f + ' 看板=[' + $b.$f + '] JSON=[' + $t.$f + ']')
            }
        }
        $bd = @($b.dependencies | Sort-Object) -join ','
        $jd = @($t.dependencies | Sort-Object) -join ','
        if ($bd -ne $jd) { [void]$fieldIssues.Add($t.id + '.dependencies 看板=[' + $bd + '] JSON=[' + $jd + ']') }
    }
}
if ($fieldIssues.Count -eq 0) { Add-Pass '看板 baseline 与 JSON 逐字段一致' } else { Add-Fail ('看板与 JSON 存在差异：' + ($fieldIssues -join ' | ')) }

$csvIssues = New-Object System.Collections.ArrayList
foreach ($t in $json.tasks) {
    $c = $csv | Where-Object { $_.'任务ID' -eq $t.id } | Select-Object -First 1
    if ($c -eq $null) { continue }
    if ([string]$c.'状态' -ne [string]$t.status) { [void]$csvIssues.Add($t.id + '.status CSV=[' + $c.'状态' + '] JSON=[' + $t.status + ']') }
    if ([string]$c.'优先级' -ne [string]$t.priority) { [void]$csvIssues.Add($t.id + '.priority CSV=[' + $c.'优先级' + '] JSON=[' + $t.priority + ']') }
    if ([string]$c.'负责人' -ne [string]$t.owner) { [void]$csvIssues.Add($t.id + '.owner CSV=[' + $c.'负责人' + '] JSON=[' + $t.owner + ']') }
    if ([math]::Abs([double]$c.'权重(百分点)' - [double]$t.weight) -gt 0.0005) {
        [void]$csvIssues.Add($t.id + '.weight CSV=[' + $c.'权重(百分点)' + '] JSON=[' + $t.weight + ']')
    }
    $cd = ''
    if ($c.'依赖') { $cd = (@($c.'依赖'.Split(',') | ForEach-Object { $_.Trim() }) | Sort-Object) -join ',' }
    $jd = @($t.dependencies | Sort-Object) -join ','
    if ($cd -ne $jd) { [void]$csvIssues.Add($t.id + '.dependencies CSV=[' + $cd + '] JSON=[' + $jd + ']') }
    if ([string]$c.'验收标准' -ne [string]$t.acceptance) { [void]$csvIssues.Add($t.id + '.acceptance CSV=[' + $c.'验收标准' + '] JSON=[' + $t.acceptance + ']') }
}
if ($csvIssues.Count -eq 0) { Add-Pass 'CSV 与 JSON 状态/优先级/负责人/权重/依赖/验收标准一致' } else { Add-Fail ('CSV 与 JSON 存在差异：' + ($csvIssues -join ' | ')) }

# ---------------------------------------------------------------- 3. 权重口径
$totalWeight = ($json.tasks | Measure-Object -Property weight -Sum).Sum
$p0 = @($json.tasks | Where-Object { $_.priority -eq 'P0' })
$p1 = @($json.tasks | Where-Object { $_.priority -eq 'P1' })
$p0Weight = ($p0 | Measure-Object -Property weight -Sum).Sum
$p1Weight = ($p1 | Measure-Object -Property weight -Sum).Sum
Add-Info ('权重：总计 ' + $totalWeight + '；P0 ' + $p0.Count + ' 项 = ' + $p0Weight + '；P1 ' + $p1.Count + ' 项 = ' + $p1Weight)
if ([math]::Abs($totalWeight - 100) -lt 0.005) { Add-Pass '权重合计 = 100' } else { Add-Fail ('权重合计应为 100，实际 ' + $totalWeight) }
if ([math]::Abs($p0Weight - 80) -lt 0.005) { Add-Pass 'P0 权重合计 = 80' } else { Add-Fail ('P0 权重合计应为 80，实际 ' + $p0Weight) }
if ([math]::Abs($p1Weight - 20) -lt 0.005) { Add-Pass 'P1 权重合计 = 20' } else { Add-Fail ('P1 权重合计应为 20，实际 ' + $p1Weight) }
if ($p0.Count -eq 23 -and $p1.Count -eq 6) { Add-Pass 'P0 23 项 / P1 6 项' } else { Add-Fail ('P0/P1 任务数应为 23/6，实际 ' + $p0.Count + '/' + $p1.Count) }

# ---------------------------------------------------------------- 4. 依赖闭合
$stageOf = @{ 'M00' = 'S0'; 'M01' = 'S1'; 'M02' = 'S2'; 'M03' = 'S2'; 'M04' = 'S3'; 'M05' = 'S4'; 'M06' = 'S4'; 'M07' = 'S5'; 'M08' = 'S5' }
$stageOrder = @{ 'S0' = 0; 'S1' = 1; 'S2' = 2; 'S3' = 3; 'S4' = 4; 'S5' = 5 }

$depIssues = New-Object System.Collections.ArrayList
foreach ($t in $json.tasks) {
    foreach ($d in $t.dependencies) {
        if ($jsonIds -notcontains $d) {
            [void]$depIssues.Add($t.id + ' 依赖不存在的任务 ' + $d)
            continue
        }
        $stageT = $stageOf[$t.id.Substring(0, 3)]
        $stageD = $stageOf[$d.Substring(0, 3)]
        if ($stageOrder[$stageD] -gt $stageOrder[$stageT]) {
            [void]$depIssues.Add($t.id + '(' + $stageT + ') 依赖后续阶段任务 ' + $d + '(' + $stageD + ')')
        }
    }
}
if ($depIssues.Count -eq 0) { Add-Pass '依赖均存在且不依赖后续阶段' } else { Add-Fail ('依赖问题：' + ($depIssues -join ' | ')) }

# 环检测（迭代 DFS）
$color = @{}
foreach ($id in $jsonIds) { $color[$id] = 0 }
$cycleFound = $false
foreach ($rootId in $jsonIds) {
    if ($color[$rootId] -ne 0) { continue }
    $stack = New-Object System.Collections.Stack
    $path = New-Object System.Collections.ArrayList
    $stack.Push(@($rootId, 0))
    while ($stack.Count -gt 0) {
        $frame = $stack.Peek()
        $nodeId = $frame[0]
        $idx = $frame[1]
        if ($idx -eq 0) { $color[$nodeId] = 1; [void]$path.Add($nodeId) }
        $node = $json.tasks | Where-Object { $_.id -eq $nodeId } | Select-Object -First 1
        $deps = @($node.dependencies)
        if ($idx -lt $deps.Count) {
            $frame[1] = $idx + 1
            $dn = $deps[$idx]
            if ($color[$dn] -eq 1) { $cycleFound = $true; break }
            if ($color[$dn] -eq 0) { $stack.Push(@($dn, 0)) }
        } else {
            $color[$nodeId] = 2
            [void]$stack.Pop()
            if ($path.Count -gt 0) { $path.RemoveAt($path.Count - 1) }
        }
    }
    if ($cycleFound) { break }
}
if ($cycleFound) { Add-Fail '依赖图中存在环' } else { Add-Pass '依赖图无环' }

# ---------------------------------------------------------------- 5. 状态纪律
$doing = @($json.tasks | Where-Object { $_.status -eq 'DOING' })
if ($doing.Count -le 1) { Add-Pass ('同一时刻 DOING 任务数 = ' + $doing.Count + '（<=1）') } else { Add-Fail ('同一时刻只能有一个 DOING，实际 ' + $doing.Count + '：' + (($doing.id) -join ',')) }

$statusIssues = New-Object System.Collections.ArrayList
foreach ($t in $json.tasks) {
    $depsAllDone = $true
    foreach ($d in $t.dependencies) {
        $dt = $json.tasks | Where-Object { $_.id -eq $d } | Select-Object -First 1
        if ($dt -eq $null -or $dt.status -ne 'DONE') { $depsAllDone = $false }
    }
    if ($t.status -eq 'READY' -and -not $depsAllDone) {
        [void]$statusIssues.Add($t.id + ' 状态 READY 但前置依赖未全部 DONE')
    }
    if (@('DOING', 'REVIEW', 'TESTED', 'DONE') -contains $t.status -and -not $depsAllDone) {
        [void]$statusIssues.Add($t.id + ' 状态 ' + $t.status + ' 但前置依赖未全部 DONE')
    }
    if (@('TESTED', 'DONE') -contains $t.status -and [string]::IsNullOrWhiteSpace([string]$t.evidence)) {
        [void]$statusIssues.Add($t.id + ' 状态 ' + $t.status + ' 但未填写验收证据')
    }
    if ($t.status -eq 'DONE' -and [string]::IsNullOrWhiteSpace([string]$t.finished_at)) {
        [void]$statusIssues.Add($t.id + ' 状态 DONE 但未填写完成日期')
    }
}
if ($statusIssues.Count -eq 0) { Add-Pass '状态纪律：READY/DOING/REVIEW/TESTED/DONE 前置与证据要求满足' } else { Add-Fail ('状态问题：' + ($statusIssues -join ' | ')) }

# ---------------------------------------------------------------- 6. docs/02 对照
$doc02Rows = @{}
foreach ($line in $doc02) {
    if ($line -match '^\|\s*(M\d\d-\d\d)\s*\|') {
        $cells = @($line -split '\|' | ForEach-Object { $_.Trim() })
        $doc02Rows[$cells[1]] = @{ title = $cells[2]; deps = $cells[3]; acceptance = $cells[4] }
    }
}
$doc02Issues = New-Object System.Collections.ArrayList
foreach ($t in $json.tasks) {
    if (-not $doc02Rows.ContainsKey($t.id)) { [void]$doc02Issues.Add('docs/02 缺少 ' + $t.id); continue }
    $row = $doc02Rows[$t.id]
    $dd = @()
    if ($row.deps -ne '无' -and $row.deps -ne '') { $dd = @($row.deps.Split(',') | ForEach-Object { $_.Trim() }) }
    $d1 = @($dd | Sort-Object) -join ','
    $d2 = @($t.dependencies | Sort-Object) -join ','
    if ($d1 -ne $d2) { [void]$doc02Issues.Add($t.id + ' 依赖 docs/02=[' + $d1 + '] JSON=[' + $d2 + ']') }
    if ($row.acceptance -ne $t.acceptance) { [void]$doc02Issues.Add($t.id + ' 验收标准与 docs/02 不一致') }
    if ($row.title -ne $t.title) { [void]$doc02Issues.Add($t.id + ' 名称与 docs/02 不一致') }
}
if ($doc02Issues.Count -eq 0) { Add-Pass 'docs/02 与 JSON 的名称/依赖/验收标准一致' } else { Add-Fail ('docs/02 差异：' + ($doc02Issues -join ' | ')) }

# ---------------------------------------------------------------- 7. docs/12 权重
$doc12Issues = New-Object System.Collections.ArrayList
foreach ($m in [regex]::Matches($doc12, '\*\*(M\d\d-\d\d)[^*]*\*\*（([\d.]+)%）')) {
    $id = $m.Groups[1].Value
    $w = [double]$m.Groups[2].Value
    $t = $json.tasks | Where-Object { $_.id -eq $id } | Select-Object -First 1
    if ($t -ne $null -and [math]::Abs($w - [double]$t.weight) -gt 0.0005) {
        [void]$doc12Issues.Add($id + ' docs12=' + $w + ' JSON=' + $t.weight)
    }
}
if ($doc12Issues.Count -eq 0) { Add-Pass 'docs/12 权重与 JSON 一致' } else { Add-Fail ('docs/12 权重差异：' + ($doc12Issues -join ' | ')) }

# ---------------------------------------------------------------- 汇总
$statusCounts = @{}
foreach ($t in $json.tasks) {
    if ($statusCounts.ContainsKey($t.status)) { $statusCounts[$t.status] = $statusCounts[$t.status] + 1 } else { $statusCounts[$t.status] = 1 }
}
$statusLine = (@($statusCounts.Keys | Sort-Object | ForEach-Object { $_ + '=' + $statusCounts[$_] })) -join ', '
Add-Info ('状态分布：' + $statusLine)

$doneWeight = 0.0
foreach ($t in $json.tasks) {
    if ($t.status -eq 'DONE' -and -not [string]::IsNullOrWhiteSpace([string]$t.evidence)) { $doneWeight = $doneWeight + [double]$t.weight }
}
Add-Info ('按 DONE+证据 计算的加权完成度：' + [math]::Round($doneWeight, 3) + '%')

Write-Host ''
if ($failures.Count -eq 0) {
    Write-Host ('校验结论：PASS（' + $passCount + ' 项通过，0 项失败）') -ForegroundColor Green
    exit 0
} else {
    Write-Host ('校验结论：FAIL（' + $passCount + ' 项通过，' + $failures.Count + ' 项失败）') -ForegroundColor Red
    exit 1
}