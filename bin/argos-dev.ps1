# open-argos dev entrypoint (Windows natif)
$ErrorActionPreference = "Stop"
# PS 7.4+ : sans ceci, un exit code non nul de python (2=error, 3=needs_human)
# deviendrait une erreur terminante et écraserait la sémantique d'exit d'argos.
$PSNativeCommandUseErrorActionPreference = $false
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:ARGOS_CONFIG_DIR = Join-Path $Root ".config\argos-dev"
$env:ARGOS_ARTIFACT_ROOT = Join-Path $Root ".argos\sessions"
$env:ARGOS_LOCK_ROOT = Join-Path $Root ".argos\locks"
& python (Join-Path $Root "argos\argos.py") @args
exit $LASTEXITCODE
