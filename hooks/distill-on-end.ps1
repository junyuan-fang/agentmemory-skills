<#
  SessionEnd hook (Windows / PowerShell) — "关闭即沉淀".
  Claude Code 在会话结束时把一段 JSON 从 stdin 传入,含 transcript_path / session_id。
  本脚本把这两个值交给 distill-worker.ps1 后台执行(索引 + 提炼),不阻塞退出。
  安装见 hooks/README.md(或直接跑仓库根目录的 install.ps1 自动装好)。
#>
$ErrorActionPreference = "SilentlyContinue"
$WORKER = Join-Path $PSScriptRoot "distill-worker.ps1"

$raw = [Console]::In.ReadToEnd()
try { $o = $raw | ConvertFrom-Json } catch { exit 0 }
$transcript = "$($o.transcript_path)"
$sid        = "$($o.session_id)"
if (-not $transcript) { exit 0 }

# 后台 detach。参数拼成单字符串并手动加引号:Start-Process 不会自动给含空格的
# 参数加引号,-File + 显式引号是唯一对带空格路径稳妥的传法。
$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$WORKER`" -Transcript `"$transcript`" -Sid `"$sid`""
Start-Process powershell -WindowStyle Hidden -ArgumentList $argLine | Out-Null
exit 0
