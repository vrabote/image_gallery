@echo off
chcp 65001 >nul
title Публикатор клипов и фото
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 goto trypython
py -3 run_gui.pyw
goto end

:trypython
where python >nul 2>nul
if errorlevel 1 goto nopython
python run_gui.pyw
goto end

:nopython
echo Не найден Python.
echo Установите его с https://www.python.org/downloads/windows/
echo При установке отметьте "Add python.exe to PATH" и "tcl/tk and IDLE".
pause

:end
