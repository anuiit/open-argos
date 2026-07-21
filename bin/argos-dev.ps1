# open-argos dev entrypoint (native Windows). ASCII-only: PS 5.1 misreads UTF-8 without BOM.
$ErrorActionPreference = "Stop"
# PS 7.4+: without this, a non-zero python exit code (2=error, 3=needs_human)
# would become a terminating error and clobber argos exit-code semantics.
$PSNativeCommandUseErrorActionPreference = $false
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:ARGOS_CONFIG_DIR = Join-Path $Root ".config\argos-dev"
$env:ARGOS_ARTIFACT_ROOT = Join-Path $Root ".argos\sessions"
$env:ARGOS_LOCK_ROOT = Join-Path $Root ".argos\locks"
& python (Join-Path $Root "argos\argos.py") @args
exit $LASTEXITCODE
