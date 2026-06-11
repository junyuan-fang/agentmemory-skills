<#
  ccskill (PowerShell) — agentmemory-skills 统一命令行入口 (Windows 原生)。
  用法与 bash 版一致:
    ccskill recall "关键词" [--summary]
    ccskill index | extract --date <d> | profile [--update]
    ccskill context --person <name> | archive --date <d> | list | show <slug> | sync
#>
$ErrorActionPreference = "Stop"
# python 子进程输出 UTF-8;不设的话 PS 5.1 按 OEM 码页解码,中文会乱
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$REPO = if ($env:AGENTMEMORY_REPO) { $env:AGENTMEMORY_REPO } else { Split-Path -Parent $PSScriptRoot }
$PY   = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$S    = Join-Path $REPO "scripts"
$DATA = Join-Path $REPO "data"
# 技能沉淀在 Claude Code 全局技能目录(新会话自动读取),与 extract-skill.py 一致
$SKILLS = if ($env:AGENTMEMORY_SKILLS_DIR) { $env:AGENTMEMORY_SKILLS_DIR } else { Join-Path $HOME ".claude\skills" }

$cmd  = if ($args.Count -ge 1) { $args[0] } else { "help" }
# @() 必须:单元素数组会被 PS 自动解包成标量,$rest[0] 就变成取首字符了
$rest = @(if ($args.Count -ge 2) { $args[1..($args.Count-1)] } else { @() })

switch ($cmd) {
  "recall"  { & $PY (Join-Path $S "query-history.py") @rest }
  "status"  { & $PY (Join-Path $S "status.py") @rest }
  "doctor"  { & $PY (Join-Path $S "status.py") @rest }
  "index"   { & $PY (Join-Path $S "index-sessions.py") @rest }
  "extract" { & $PY (Join-Path $S "extract-skill.py") @rest }
  "context" { & $PY (Join-Path $S "cross-platform-context.py") @rest }
  "archive" { & $PY (Join-Path $S "archive-session.py") @rest }
  "profile" {
    if ($rest.Count -ge 1 -and ($rest[0] -eq "--update" -or $rest[0] -eq "-u")) {
      $r2 = if ($rest.Count -ge 2) { $rest[1..($rest.Count-1)] } else { @() }
      & $PY (Join-Path $S "update-user-profile.py") --days 7 --per-user @r2
    }
    $p = Join-Path $DATA "user-profile.md"
    # -Encoding UTF8:文件是 python 写的无 BOM UTF-8,PS 5.1 默认按 ANSI 读会乱码
    if (Test-Path $p) { Get-Content $p -Encoding UTF8 } else { "(none yet — run: ccskill profile --update)" }
  }
  "list"    {
    Get-ChildItem -Directory $SKILLS -ErrorAction SilentlyContinue | ForEach-Object {
      $sk = Join-Path $_.FullName "SKILL.md"
      if (Test-Path $sk) {
        $desc = ""
        $hit = Get-Content $sk -Encoding UTF8 | Where-Object { $_ -match '^description:\s*(.+)$' } | Select-Object -First 1
        if ($hit -and ($hit -match '^description:\s*(.+)$')) { $desc = $Matches[1] }
        "{0,-32} {1}" -f $_.Name, $desc
      }
    }
  }
  "show"    {
    if ($rest.Count -lt 1) { "usage: ccskill show <slug>"; exit 1 }
    Get-Content (Join-Path $SKILLS ($rest[0] + "\SKILL.md")) -Encoding UTF8
  }
  "sync"    { Push-Location $REPO; git pull --rebase --autostash; git push; Pop-Location }
  default   {
    @"
ccskill (PowerShell) — agentmemory-skills
  status                    自检:hook/计划任务/索引 是否都装好
  recall <kw> [--summary]   搜历史(可选 LLM 摘要)
  index                     索引 / 增量更新
  extract --date <d>        从对话提炼技能
  profile [--update]        查看 / 刷新用户画像
  context --person <name>   跨平台上下文
  archive --date <d>        导出某天对话
  list | show <slug>        列出 / 查看技能
  sync                      git pull + push
"@
  }
}
