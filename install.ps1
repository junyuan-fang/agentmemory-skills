<#
  agentmemory-skills 一键安装(Windows 原生 PowerShell)。
  装完即全自动:关闭会话自动沉淀 + 每日计划任务沉淀 + 斜杠命令可用。
  幂等:重复跑安全。卸载:  powershell -File install.ps1 -Uninstall

  若提示执行策略限制,用:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
#>
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$REPO    = $PSScriptRoot
$S       = Join-Path $REPO "scripts"
$PY      = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PY) { $PY = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
$HOOK    = Join-Path $REPO "hooks\distill-on-end.ps1"
$CMDDIR  = Join-Path $HOME ".claude\commands"
$TASKDIR = Join-Path $REPO "data\tasks"
$TASKS   = @("AgentMemory-Index","AgentMemory-Archive","AgentMemory-Extract","AgentMemory-Profile")

function Remove-FromPath($dir) {
  $p = [Environment]::GetEnvironmentVariable("Path","User")
  if ($p -and ($p -split ';' -contains $dir)) {
    $new = ($p -split ';' | Where-Object { $_ -ne $dir }) -join ';'
    [Environment]::SetEnvironmentVariable("Path",$new,"User")
  }
}

if ($Uninstall) {
  Write-Host "卸载 agentmemory-skills…"
  if ($PY) { & $PY (Join-Path $S "install_hook.py") --remove --command $HOOK }
  # 经 cmd 包一层:PS 5.1 在 $ErrorActionPreference=Stop 下重定向原生命令的
  # stderr 会直接抛 NativeCommandError,任务不存在时整个卸载就断了
  foreach ($t in $TASKS) { cmd /c "schtasks /Delete /TN $t /F >nul 2>&1" }
  Remove-FromPath $S
  # 移除 CLAUDE.md 里的画像 import(沉淀在 ~\.claude\skills 的技能保留,属于你的数据)
  $claudeMd = Join-Path $HOME ".claude\CLAUDE.md"
  if (Test-Path $claudeMd) {
    $import = "@" + (Join-Path $REPO "data\user-profile.md")
    $kept = Get-Content $claudeMd -Encoding UTF8 | Where-Object {
      $_ -ne $import -and $_ -ne "# agentmemory-skills: 用户画像自动注入"
    }
    Set-Content -Path $claudeMd -Value $kept -Encoding UTF8
  }
  Write-Host "完成。"
  exit 0
}

if (-not $PY) { Write-Error "找不到 python,请先安装 Python 3 并加入 PATH。"; exit 1 }
Write-Host "==> 安装 agentmemory-skills (repo: $REPO)"

# 1) 把 scripts 加进用户 PATH,使 `ccskill` (ccskill.cmd) 任意目录可用
$userPath = [Environment]::GetEnvironmentVariable("Path","User")
if (-not $userPath) { $userPath = "" }
if (-not ($userPath -split ';' -contains $S)) {
  [Environment]::SetEnvironmentVariable("Path", (($userPath.TrimEnd(';') + ';' + $S).TrimStart(';')), "User")
  Write-Host "  ✓ 已把 $S 加入用户 PATH(新开终端后 ccskill 生效)"
} else { Write-Host "  ✓ scripts 已在 PATH" }

# 2) 斜杠命令
New-Item -ItemType Directory -Force -Path $CMDDIR | Out-Null
Copy-Item (Join-Path $REPO "commands\*.md") $CMDDIR -Force
Write-Host "  ✓ 斜杠命令 → $CMDDIR ( /recall /skill-extract /profile /cross-context )"

# 3) SessionEnd hook(关闭即沉淀)—— 用 powershell 调 .ps1 作为 hook 命令
$hookCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$HOOK`""
& $PY (Join-Path $S "install_hook.py") --command $hookCmd

# 4) 首次建立索引(不要重定向 stderr:PS 5.1 + EAP=Stop 下会抛 NativeCommandError)
Write-Host "  … 索引已有的 Claude Code 会话"
& $PY (Join-Path $S "index-sessions.py") | Out-Null
Write-Host "  ✓ 索引完成"

# 5) 定时沉淀:为每个任务生成无参 .cmd 包装(避免 schtasks 引号地狱),再注册计划任务
New-Item -ItemType Directory -Force -Path $TASKDIR | Out-Null
$LOG = Join-Path $REPO "data\cron.log"
function Make-TaskCmd($name, $line) {
  $f = Join-Path $TASKDIR "$name.cmd"
  # Default(ANSI) 而非 ASCII:路径里有中文用户名时 ASCII 会写成 '?'
  "@echo off`r`n$line >> `"$LOG`" 2>&1" | Set-Content -Encoding Default $f
  return $f
}
# 日期一律用脚本自己支持的 --date yesterday(%DATE% 的格式随系统区域变,不可靠)
$idx  = Make-TaskCmd "index"   "`"$PY`" `"$S\index-sessions.py`""
$arc  = Make-TaskCmd "archive" "`"$PY`" `"$S\archive-session.py`" --date yesterday"
$ext  = Make-TaskCmd "extract" "`"$PY`" `"$S\extract-skill.py`" --date yesterday"
$prof = Make-TaskCmd "profile" "`"$PY`" `"$S\update-user-profile.py`" --days 7 --per-user"

schtasks /Create /F /TN $TASKS[0] /SC HOURLY            /TR $idx  | Out-Null
schtasks /Create /F /TN $TASKS[1] /SC DAILY /ST 03:10   /TR $arc  | Out-Null
schtasks /Create /F /TN $TASKS[2] /SC DAILY /ST 03:30   /TR $ext  | Out-Null
schtasks /Create /F /TN $TASKS[3] /SC DAILY /ST 04:00   /TR $prof | Out-Null
Write-Host "  ✓ 计划任务已装(每小时索引 / 03:10 归档 / 03:30 提炼 / 04:00 画像)"

# 6) 画像自动注入:往全局 CLAUDE.md 加一行 @import,每个新会话自动带上画像
$claudeMd  = Join-Path $HOME ".claude\CLAUDE.md"
$profileMd = Join-Path $REPO "data\user-profile.md"
if (-not (Test-Path $profileMd)) {
  "# 用户画像`r`n`r`n(尚未生成 — 跑 ccskill profile --update)" | Set-Content -Encoding UTF8 $profileMd
}
$import = "@$profileMd"
$existing = if (Test-Path $claudeMd) { Get-Content $claudeMd -Encoding UTF8 } else { @() }
if ($existing -notcontains $import) {
  Add-Content -Path $claudeMd -Encoding UTF8 -Value "`r`n# agentmemory-skills: 用户画像自动注入`r`n$import"
  Write-Host "  ✓ 画像 import → $claudeMd"
} else { Write-Host "  ✓ 画像 import 已在 CLAUDE.md" }

Write-Host ""
Write-Host "✅ 装好了,之后全自动,无需任何手动操作:"
Write-Host "   · 关闭 Claude 会话 → 自动索引 + 提炼(SessionEnd hook)"
Write-Host "   · 每天后台         → 提炼技能 + 刷新画像(计划任务)"
Write-Host "   · 随时             → ccskill recall / extract / profile"
Write-Host ""
Write-Host "新开一个终端后试:  ccskill recall `"你聊过的某个话题`""
Write-Host "卸载:  powershell -File `"$REPO\install.ps1`" -Uninstall"
