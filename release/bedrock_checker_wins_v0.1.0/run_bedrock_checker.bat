@echo off
REM bedrock_checker_wins v0.1.0 -- portable launcher.
REM chcp 65001 first: the exe logs UTF-8, a stock console is cp1252.
chcp 65001 >nul 2>&1
setlocal
title bedrock_checker_wins v0.1.0

REM Always run from the folder holding this script, whatever the caller's cwd.
cd /d "%~dp0"

echo ============================================================
echo  bedrock_checker_wins  v0.1.0
echo ============================================================
echo  Folder : %CD%
echo.
echo  Settings: per config.json (ships as hours=24, regions us-east-1 + ap-southeast-1)
echo  Credentials: EVAL_AWS_ACCESS_KEY_ID / EVAL_AWS_SECRET_ACCESS_KEY env vars
echo  (never stored in config.json).
echo.
REM %~dp0 in front of the exe: a bare name dies with 9009 on hardened images
REM where NoDefaultCurrentDirectoryInExePath excludes the current directory.
if not exist "%~dp0bedrock_checker_wins.exe" (
    echo ERROR: bedrock_checker_wins.exe not found next to this script.
    echo Unzip the whole release folder and keep the files together.
    echo.
    pause
    exit /b 1
)

echo Starting bedrock_checker_wins.exe ...
echo ------------------------------------------------------------
"%~dp0bedrock_checker_wins.exe" %*
set "RC=%ERRORLEVEL%"
echo ------------------------------------------------------------
if not "%RC%"=="0" (
    echo bedrock_checker_wins exited with code %RC%.
    echo See DEPLOY_README.md for troubleshooting.
    pause
    exit /b %RC%
)
echo bedrock_checker_wins stopped.
endlocal
