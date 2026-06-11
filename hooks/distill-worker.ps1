<#
  distill-on-end.ps1 的后台 worker:索引刚结束的 transcript,再提炼技能。
  由 hook detach 调起(-File 传参,路径带空格也安全);直接手跑也无害:
    powershell -File distill-worker.ps1 -Transcript "C:\...\xxx.jsonl" -Sid "abc"
#>
param(
  [Parameter(Mandatory=$true)][string]$Transcript,
  [string]$Sid = ""
)
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$REPO = if ($env:AGENTMEMORY_REPO) { $env:AGENTMEMORY_REPO } else { Split-Path -Parent $PSScriptRoot }
$PY   = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$LOG  = Join-Path $REPO "data\cron.log"

New-Item -ItemType Directory -Force -Path (Join-Path $REPO "data") | Out-Null

"[distill $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] session=$Sid transcript=$Transcript" |
  Out-File -Append -Encoding utf8 $LOG

& $PY (Join-Path $REPO "scripts\index-sessions.py") --file $Transcript 2>&1 |
  ForEach-Object { "$_" } | Out-File -Append -Encoding utf8 $LOG

# 嫌每次关会话都提炼太重的话,注释掉下面这段,提炼交给每天的计划任务
if ($Sid) {
  & $PY (Join-Path $REPO "scripts\extract-skill.py") --session $Sid 2>&1 |
    ForEach-Object { "$_" } | Out-File -Append -Encoding utf8 $LOG
}
