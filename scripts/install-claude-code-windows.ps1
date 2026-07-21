# install-claude-code-windows.ps1 — installe open-argos pour Claude Code (Windows natif)
#   1) shim CLI global `argos` dans %USERPROFILE%\bin (ajouté au PATH utilisateur)
#   2) skill Claude Code dans %USERPROFILE%\.claude\skills\argos
#   3) répertoires runtime %USERPROFILE%\.argos\{sessions,locks}
# Usage : powershell -ExecutionPolicy Bypass -File F:\dev\open-argos\scripts\install-claude-code-windows.ps1
$ErrorActionPreference = "Stop"

$Root = "F:\dev\open-argos"
if (-not (Test-Path (Join-Path $Root "argos\argos.py"))) {
    throw "open-argos introuvable a $Root — lance d'abord scripts/migrate-to-argos.sh dans WSL."
}
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "python introuvable dans le PATH — installe Python 3 (python.org ou winget install Python.Python.3.12)." }

# 1) Shim CLI global
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
    Write-Host "PATH utilisateur: $BinDir ajoute (ouvre un NOUVEAU terminal)."
}

# 2) Skill Claude Code
$SkillDir = Join-Path $env:USERPROFILE ".claude\skills\argos"
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
Copy-Item (Join-Path $Root "argos-tools\claude-code\SKILL.md") (Join-Path $SkillDir "SKILL.md") -Force
Write-Host "skill Claude Code: $SkillDir\SKILL.md"

# 3) Runtime
foreach ($d in @(".argos\sessions", ".argos\locks")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE $d) | Out-Null
}

Write-Host ""
Write-Host "Installation terminee. Verification (nouveau terminal) :"
Write-Host "  argos doctor --json"
Write-Host "Claude Code detectera le skill 'argos' automatiquement (~/.claude/skills/argos)."
