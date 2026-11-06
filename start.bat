@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

if not exist ".runtime\Scripts\python.exe" goto find_py
".runtime\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 goto find_py
".runtime\Scripts\python.exe" -B "%~dp0launch.py" %*
goto done

:find_py
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 goto find_python
py -3 -B "%~dp0launch.py" %*
goto done

:find_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
python -B "%~dp0launch.py" %*
goto done

:missing_python
echo Python 3.11 or newer is required.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH", then double-click start.bat again.
pause
exit /b 1

:done
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
