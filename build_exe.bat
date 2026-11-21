@echo off
chcp 65001 >nul
cd /d "%~dp0"
title X11 Battery - збірка exe

set PY=py
where py >nul 2>nul || set PY=python
where %PY% >nul 2>nul
if errorlevel 1 (
    echo Python не знайдено. Встанови Python 3 з python.org ^(з галочкою Add to PATH^).
    pause
    exit /b 1
)

echo Закриваю запущену програму ^(якщо вона працює^)...
taskkill /f /im X11Battery.exe >nul 2>nul

echo.
echo Встановлюю PyInstaller...
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto fail

echo.
echo Збираю exe...
if not exist "%~dp0X11Battery.ico" goto noicon
echo Іконка: X11Battery.ico знайдена, додаю в exe.
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --name X11Battery --version-file version_info.txt --icon "%~dp0X11Battery.ico" --add-data "%~dp0X11Battery.ico;." x11_battery.py
goto built
:noicon
echo УВАГА: файл X11Battery.ico не знайдено поруч з build_exe.bat - збираю БЕЗ іконки!
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --name X11Battery --version-file version_info.txt x11_battery.py
:built
if errorlevel 1 goto fail

copy /y "dist\X11Battery.exe" "X11Battery.exe" >nul
if errorlevel 1 goto fail
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q X11Battery.spec 2>nul

echo.
echo Оновлюю кеш іконок Windows...
ie4uinit.exe -ClearIconCache >nul 2>nul
ie4uinit.exe -show >nul 2>nul

echo.
echo Готово: X11Battery.exe лежить поруч з цим файлом. Запусти його.
pause
exit /b 0

:fail
echo.
echo Помилка збірки. Прокрути вікно вгору й подивись повідомлення.
pause
exit /b 1
