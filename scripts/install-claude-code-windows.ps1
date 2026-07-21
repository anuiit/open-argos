# install-claude-code-windows.ps1 - installs open-argos for Claude Code (native Windows)
#   1) global `argos` CLI shim in %USERPROFILE%\bin (added to user PATH)
#   2) Claude Code skill in %USERPROFILE%\.claude\skills\argos
#   3) runtime dirs %USERPROFILE%\.argos\{sessions,locks}
# Usage: powershell -ExecutionPolicy Bypass -File F:\dev\open-argos\scripts\install-claude-code-windows.ps1
# NOTE: ASCII-only on purpose - Windows PowerShell 5.1 misreads UTF-8 without BOM.
$ErrorActionPreference = "Stop"

$Root = "F:\dev\open-argos"
if (-not (Test-Path (Join-Path $Root "argos\argos.py"))) {
    throw "open-argos not found at $Root - run the WSL sync first (scripts/migrate-to-argos.sh) or git clone https://github.com/anuiit/open-argos.git"
}
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "python not found in PATH - install Python 3 (python.org or: winget install Python.Python.3.12)" }

# 1) Global CLI shim
$BinDir = Join-Path $env:USERPROFILE "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$shim = @(
    '@echo off',
    ('set "ARGOS_ROOT=' + $Root + '"'),
    'set "ARGOS_CONFIG_DIR=%ARGOS_ROOT%\.config\argos-dev"',
    'set "ARGOS_ARTIFACT_ROOT=%USERPROFILE%\.argos\sessions"',
    'set "ARGOS_LOCK_ROOT=%USERPROFILE%\.argos\locks"',
    'python "%ARGOS_ROOT%\argos\argos.py" %*'
) -join "`r`n"
Set-Content -Path (Join-Path $BinDir "argos.cmd") -Value $shim -Encoding ASCII
Write-Host "shim: $BinDir\argos.cmd -> $Root"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $BinDir) {
    [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(";") + ";" + $BinDir), "User")
    Write-Host "user PATH: added $BinDir (open a NEW terminal)."
}

# 2) Claude Code skill
$SkillDir = Join-Path $env:USERPROFILE ".claude\skills\argos"
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
Copy-Item (Join-Path $Root "argos-tools\claude-code\SKILL.md") (Join-Path $SkillDir "SKILL.md") -Force
Write-Host "Claude Code skill: $SkillDir\SKILL.md"

# 3) Runtime dirs
foreach ($d in @(".argos\sessions", ".argos\locks")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE $d) | Out-Null
}

Write-Host ""
Write-Host "Done. Verify in a NEW terminal:"
Write-Host "  argos doctor --json"
Write-Host "Claude Code will auto-detect the 'argos' skill (%USERPROFILE%\.claude\skills\argos)."
