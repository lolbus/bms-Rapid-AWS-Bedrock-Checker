@echo off
REM ===================================================================
REM  build_exe.bat -- build a portable Windows exe from a uv project.
REM
REM  Drop this beside pyproject.toml and edit the two SET lines below.
REM  Run from anywhere: it cd's to its own folder first.
REM
REM  What it does, and why each step is here:
REM    1. checks uv is on PATH (bootstraps it if not)
REM    2. uv sync --dev            -> the locked env PyInstaller must analyse
REM    3. wipes dist\ and build\   -> a stale analysis cache produces an exe
REM                                   missing a module the spec correctly names
REM    4. runs PyInstaller through the PROJECT venv, not the ambient python
REM    5. ASSERTS the artifact exists -- PyInstaller can print warnings, exit 0
REM                                   and have produced nothing
REM    6. runs the exe's --selftest so a broken build fails here, not in the field
REM ===================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

REM ---- EDIT THESE TWO ------------------------------------------------
set "APP_NAME=bedrock_checker_wins"
set "APP_MODE=onedir"
REM         ^ onedir (exe + _internal\, required for sidecar payloads)
REM           or onefile (single self-extracting exe, small GUI clients)
REM -------------------------------------------------------------------

set "SPEC=%APP_NAME%.spec"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if /i "%APP_MODE%"=="onefile" (
    set "ARTIFACT=%CD%\dist\%APP_NAME%.exe"
) else (
    set "ARTIFACT=%CD%\dist\%APP_NAME%\%APP_NAME%.exe"
)

echo ============================================================
echo  building %APP_NAME% (%APP_MODE%)
echo  project: %CD%
echo ============================================================

REM ---- 1. uv -------------------------------------------------------
where uv >nul 2>&1
if errorlevel 1 (
    echo [..] uv not on PATH; installing to %%USERPROFILE%%\.local\bin
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>&1
    if errorlevel 1 (
        echo ERROR: uv still not found. Install it and re-run.
        exit /b 1
    )
)
for /f "delims=" %%v in ('uv --version') do echo [ok] %%v

REM ---- 2. sync -----------------------------------------------------
echo [..] uv sync --dev
uv sync --dev
if errorlevel 1 (
    echo ERROR: uv sync failed. Fix pyproject.toml / uv.lock first.
    exit /b 1
)
if not exist "%VENV_PY%" (
    echo ERROR: no %VENV_PY% after uv sync.
    exit /b 1
)

REM PyInstaller is a dev dependency, not a global tool: the version that built
REM this artifact must be the one recorded in uv.lock.
"%VENV_PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller is not in the project venv.
    echo Add it:  uv add --dev pyinstaller
    exit /b 1
)

REM ---- 3. clean ----------------------------------------------------
if exist "%CD%\dist"  rmdir /s /q "%CD%\dist"
if exist "%CD%\build" rmdir /s /q "%CD%\build"
echo [ok] wiped dist\ and build\

REM ---- 4. build ----------------------------------------------------
if not exist "%SPEC%" (
    echo ERROR: %SPEC% not found. Render it from templates\app.spec.tmpl.
    exit /b 1
)
echo [..] PyInstaller %SPEC%
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "VIRTUAL_ENV=%CD%\.venv"
"%VENV_PY%" -m PyInstaller "%SPEC%" --clean --noconfirm ^
    --distpath "%CD%\dist" --workpath "%CD%\build"
if errorlevel 1 (
    echo ERROR: PyInstaller exited non-zero.
    exit /b 1
)

REM ---- 5. assert ---------------------------------------------------
if not exist "%ARTIFACT%" (
    echo ERROR: PyInstaller reported success but %ARTIFACT% does not exist.
    echo Check APP_NAME / APP_MODE above against the name= in %SPEC%.
    exit /b 1
)
for %%f in ("%ARTIFACT%") do set "ARTIFACT_SIZE=%%~zf"
echo [ok] %ARTIFACT% (%ARTIFACT_SIZE% bytes)

REM ---- 6. smoke ----------------------------------------------------
REM Not a substitute for verify_release.py: that one scrubs the environment,
REM which is what catches missing hidden imports. This is the fast failure.
REM DXCPACK_NO_HOLD stops a crash-hold input() from blocking a script forever.
set "DXCPACK_NO_HOLD=1"
echo [..] %APP_NAME%.exe --selftest
"%ARTIFACT%" --selftest
if errorlevel 1 (
    echo ERROR: the built exe failed its own selftest.
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD OK
echo  artifact : %ARTIFACT%
echo  next     : assemble release\%APP_NAME%_vX.Y.Z\ (SKILL.md section 6)
echo             then python templates\verify_release.py that folder
echo ============================================================
endlocal
