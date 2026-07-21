@echo off
setlocal
set "ROOT=%~dp0.."
for %%i in ("%ROOT%") do set "ROOT=%%~fi"
set "ARGOS_CONFIG_DIR=%ROOT%\.config\argos-dev"
set "ARGOS_ARTIFACT_ROOT=%ROOT%\.argos\sessions"
set "ARGOS_LOCK_ROOT=%ROOT%\.argos\locks"
python "%ROOT%\argos\argos.py" %*
exit /b %ERRORLEVEL%
