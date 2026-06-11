@echo off
REM ccskill (cmd shim) — 让 `ccskill ...` 在 cmd / PowerShell 里都能用,转发给 ccskill.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ccskill.ps1" %*
